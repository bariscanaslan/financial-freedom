"""
Egitim dongusu.

DEGISMEZ KURALLAR (bunlari gevsetme):
  1. TEST SETINE EGITIM SIRASINDA DOKUNULMAZ. Ne loss'ta, ne early
     stopping'de, ne model secmede. dataset.X_test bu dosyada GECMEZ.
     Test'e bakarak durdurmak, test'i ikinci bir validation setine
     cevirir ve raporladigin skoru yalana dondurur.
  2. Early stopping VAL uzerinde, VAL PINBALL loss'una gore.
  3. Minibatch. Full-batch degil -- gradyan gurultusu bu boyuttaki
     seride duzenlilestirici gorevi gorur.
  4. Seed sabit. Ayni cfg + ayni veri = ayni model.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from data.dataset import Dataset, Scaler

from .baselines import QuantileForecaster
from .config import ModelConfig, free_device_cache
from .device import seed_device
from .losses import pinball_loss
from .nets import QuantileLSTM

log = logging.getLogger(__name__)


# -------------------------------------------------------------------- seed
def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    seed_device(seed)  # cihaza ozel RNG -- hangi backend varsa (device.py)


# ----------------------------------------------------------- egitilmis model
@dataclass
class TrainedModel(QuantileForecaster):
    """
    Ag + scaler + cfg birlikte. UCU BIRDEN.

    Scaler'i modelden ayirmak, notebook'ta yasanan hatanin ta kendisiydi:
    scaler bellekte yasiyordu, model diske yaziliyordu. Baska bir sureçte
    yuklendiginde ag ayni ama olcek yanlis olur ve cikti sessizce coop olur
    -- patlamaz, sadece yanlis olur. En kotu hata turu.
    """

    net: QuantileLSTM
    scaler: Scaler                 # HEDEFIN scaler'i (= 0. kanal 'r')
    cfg: ModelConfig
    # Cok degiskenli girdide her kanalin kendi scaler'i vardir. predict()
    # uretimde ham OHLCV'den ozellik kurup bunlarla olcekler. Kaybedilirse
    # model calisir ama girdi yanlis olceklenir -- SESSIZ COOP.
    feature_scalers: list[Scaler] | None = None
    history: list[dict] = field(default_factory=list)
    best_epoch: int = -1
    best_val_loss: float = float("inf")

    name: str = "QuantileLSTM"

    def __post_init__(self) -> None:
        self.quantiles = tuple(self.cfg.quantiles)

    # -- QuantileForecaster arayuzu --
    def fit(self, dataset: Dataset) -> "TrainedModel":
        """Zaten egitilmis. Arayuz butunlugu icin var."""
        return self

    @torch.no_grad()
    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        """
        (N, seq_len, 1) olcekli -> (N, horizon, Q) LOG GETIRI.

        Scaler'i BURADA ters ceviriyoruz. Disariya olcekli sayi sizmaz.
        inverse afin ve artan (x*std + mean, std>0) oldugu icin quantile
        sirasi bozulmaz -- p10 < p50 < p90 ters cevrildikten sonra da gecerli.
        """
        device = self.cfg.resolve_device()
        self.net.eval().to(device)

        x = torch.as_tensor(np.asarray(X_scaled, dtype=np.float32), device=device)
        out_scaled = self.net(x).cpu().numpy()          # (N, horizon, Q)
        return self.scaler.inverse(out_scaled)          # -> log getiri


# ------------------------------------------------------------------ egitim
def _loader(X: np.ndarray, y: np.ndarray, batch_size: int, shuffle: bool) -> DataLoader:
    ds = TensorDataset(
        torch.as_tensor(X, dtype=torch.float32),
        torch.as_tensor(y, dtype=torch.float32),
    )
    # shuffle: pencereler ICINDE zaman sirasi korunur (X'in kendisi bir dizi).
    # Karistirilan sey pencerelerin GORULME sirasi -- bu leakage degildir,
    # cunku her pencere zaten kendi dilimi icinde kapali bir ornektir.
    return DataLoader(
        ds,
        batch_size=batch_size,
        shuffle=shuffle,
        drop_last=False,
        num_workers=0,  # Windows'ta spawn maliyeti bu boyutta zarar
    )


def train(dataset: Dataset, cfg: ModelConfig | None = None, verbose: bool = True) -> TrainedModel:
    """
    dataset + cfg -> TrainedModel

    dataset.X_test / y_test BU FONKSIYONDA HIC KULLANILMAZ.
    """
    cfg = cfg or ModelConfig(seq_len=dataset.seq_len, horizon=dataset.horizon)

    if cfg.seq_len != dataset.seq_len or cfg.horizon != dataset.horizon:
        raise ValueError(
            f"cfg (seq_len={cfg.seq_len}, horizon={cfg.horizon}) ile dataset "
            f"(seq_len={dataset.seq_len}, horizon={dataset.horizon}) uyusmuyor"
        )

    n_feat = dataset.X_train.shape[-1]
    if cfg.input_dim != n_feat:
        raise ValueError(
            f"cfg.input_dim={cfg.input_dim} ile dataset kanal sayisi {n_feat} "
            f"uyusmuyor. ModelConfig'i features ile birlikte kur."
        )

    seed_everything(cfg.seed)
    device = cfg.resolve_device()

    net = QuantileLSTM(
        quantiles=cfg.quantiles,
        input_dim=cfg.input_dim,
        hidden_dim=cfg.hidden_dim,
        num_layers=cfg.num_layers,
        horizon=cfg.horizon,
        dropout=cfg.dropout,
    ).to(device)

    # foreach=False: Adam'in fuse edilmis foreach_addcdiv kernel'i XPU'da
    # ard arda cok sayida model egitilirken ara sira native cokme uretiyor
    # (torch 2.13.0+xpu). Tek tek guncelleme biraz yavas ama KARARLI.
    opt = torch.optim.Adam(
        net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay, foreach=False
    )

    tr = _loader(dataset.X_train, dataset.y_train, cfg.batch_size, shuffle=True)
    va = _loader(dataset.X_val, dataset.y_val, cfg.batch_size, shuffle=False)

    if verbose:
        log.info(
            "egitim basliyor | device=%s | params=%d | train=%d val=%d",
            device, net.n_params(), len(dataset.X_train), len(dataset.X_val),
        )
        print(f"[train] device={device}  params={net.n_params():,}  "
              f"train={len(dataset.X_train)} val={len(dataset.X_val)}  "
              f"(test={len(dataset.X_test)} -- DOKUNULMUYOR)")

    best_state: dict | None = None
    best_val = float("inf")
    best_epoch = -1
    bad_epochs = 0
    history: list[dict] = []

    for epoch in range(1, cfg.max_epochs + 1):
        # ---- train ----
        net.train()
        tr_sum, tr_n = 0.0, 0
        for xb, yb in tr:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad(set_to_none=True)
            loss = pinball_loss(net(xb), yb, cfg.quantiles)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), cfg.grad_clip)
            opt.step()
            tr_sum += loss.item() * len(xb)
            tr_n += len(xb)
        tr_loss = tr_sum / max(tr_n, 1)

        # ---- validate ----
        net.eval()
        va_sum, va_n = 0.0, 0
        with torch.no_grad():
            for xb, yb in va:
                xb, yb = xb.to(device), yb.to(device)
                loss = pinball_loss(net(xb), yb, cfg.quantiles)
                va_sum += loss.item() * len(xb)
                va_n += len(xb)
        va_loss = va_sum / max(va_n, 1)

        history.append({"epoch": epoch, "train_loss": tr_loss, "val_loss": va_loss})

        # ---- early stopping (VAL uzerinde) ----
        if va_loss < best_val - 1e-6:
            best_val = va_loss
            best_epoch = epoch
            bad_epochs = 0
            # CPU'ya kopyala: cihaz belleginde tutup sonra tasimayalim
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        else:
            bad_epochs += 1

        if verbose and (epoch % 10 == 0 or epoch == 1):
            print(f"  epoch {epoch:3d}  train={tr_loss:.6f}  val={va_loss:.6f}"
                  f"{'  *' if best_epoch == epoch else ''}")

        if bad_epochs >= cfg.patience:
            if verbose:
                print(f"  early stop @ epoch {epoch} "
                      f"(en iyi: epoch {best_epoch}, val={best_val:.6f})")
            break

    # En iyi VAL agirliklarini geri yukle -- son epoch'unkileri degil.
    if best_state is not None:
        net.load_state_dict(best_state)

    # Agi CPU'ya al ve cihaz cache'ini birak. predict() gerektiginde
    # tekrar cihaza tasir. Bu olmadan coklu egitimde XPU kaynagi tukeniyor.
    net.to("cpu")
    del opt, tr, va
    free_device_cache()

    return TrainedModel(
        net=net,
        scaler=dataset.scaler,
        cfg=cfg,
        feature_scalers=getattr(dataset, "feature_scalers", None),
        history=history,
        best_epoch=best_epoch,
        best_val_loss=best_val,
    )
