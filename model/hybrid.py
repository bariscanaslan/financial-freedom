"""
Hibrit model: EWMA cipali quantile LSTM.

TESHIS (olcumle vardik, tahminle degil):
  Ozellik zenginlestirmesi ISE YARAMADI. VAL'de tek degiskenli model
  EWMA'yi +%1.66 gecerken, 9 ozellikli model +%1.77 gecti -- dokuz
  ozelligin toplam katkisi %0.1. TEST'te ikisi de sifira coktu.

  Demek ki sorun GIRDI EKSIKLIGI DEGIL. LSTM, oynakligin SEVIYESINI
  sifirdan ogrenmeye calisiyor ve beceremiyor. EWMA'nin uc satirda
  yaptigi isi, ozellik olarak onune koysan bile ogrenemiyor.

COZUM: seviyeyi ona BEDAVAYA VER.
  Hedefi o gunun EWMA sigma'sina bol:

      u_t = r_t / sigma_t          (standartlastirilmis getiri)

  Model artik "yarin ne kadar oynak olacak"i degil, "bugunku oynakliga
  GORE sekil ne" sorusunu cozer. u_t yaklasik i.i.d.'dir -- yani LSTM'in
  ogrenebilecegi bir seye benzer. Tahmin geri cevrilir:

      q_r = sigma_t * q_u

SIGORTA: model hicbir sey ogrenemezse ve q_u sabit normal quantile'lara
yakinsarsa, sonuc AYNEN EWMA olur. Yani bu mimari EWMA'dan anlamli olcude
KOTU olamaz -- en kotu ihtimalle ona esitlenir. Kazanci varsa, gercek
kazanctir: sigma'nin veremedigi bir sey (asimetri, kalin kuyruk, rejim)
ogrenilmis demektir.

NEDENSELLIK: sigma_t SADECE pencere icindeki getirilerden ve train
varyansindan hesaplanir. t+1 gunu hakkinda hicbir bilgi icermez.
"""
from __future__ import annotations

import logging

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from data.dataset import Dataset, Scaler

from .baselines import QuantileForecaster
from .config import ModelConfig, free_device_cache
from .losses import pinball_loss
from .nets import QuantileLSTM
from .train import seed_everything

log = logging.getLogger(__name__)


# ------------------------------------------------------------------- sigma
def ewma_sigma(
    X_scaled: np.ndarray,
    scaler: Scaler,
    sigma2_init: float,
    lam: float = 0.94,
    return_channel: int = 0,
) -> np.ndarray:
    """
    Her pencere icin bir sonraki gunun EWMA oynaklik tahmini.

    sigma^2_t = lam * sigma^2_{t-1} + (1-lam) * r^2_{t-1}

    baselines.EWMAVolModel ile AYNI hesap -- kasitli. Hibrit modelin
    cipasi tam olarak yenmeye calistigi seydir; adil karsilastirma icin
    ikisi ayni sigma'yi kullanmali.
    """
    x = np.asarray(X_scaled, dtype=np.float64)[..., return_channel]
    r = scaler.inverse(x)                       # (N, seq_len) ham log getiri

    sigma2 = np.full(len(r), float(sigma2_init), dtype=np.float64)
    for t in range(r.shape[1]):
        sigma2 = lam * sigma2 + (1.0 - lam) * r[:, t] ** 2

    return np.sqrt(sigma2)                      # (N,)


# ------------------------------------------------------------------- model
class HybridEWMALSTM(QuantileForecaster):
    """
    Cikti: q_r = sigma_t * q_u
      sigma_t : EWMA'dan gelir (ogrenilmez, bedava, nedensel)
      q_u     : QuantileLSTM'den gelir -- standartlastirilmis getirinin
                quantile'lari

    Quantile crossing yine YAPISAL OLARAK imkansiz: q_u siralidir
    (nets.py'deki softplus cipasi) ve sigma_t > 0 ile carpmak sirayi bozmaz.
    """

    name = "Hybrid EWMA+LSTM"

    def __init__(self, cfg: ModelConfig, lam: float = 0.94):
        self.cfg = cfg
        self.quantiles = tuple(cfg.quantiles)
        self.lam = lam

        self.net: QuantileLSTM | None = None
        self.scaler: Scaler | None = None
        self.feature_scalers: list[Scaler] | None = None
        self.sigma2_init: float = 0.0
        self.return_channel: int = 0
        self.horizon: int = cfg.horizon
        self.best_epoch: int = -1
        self.best_val_loss: float = float("inf")
        self.history: list[dict] = []

    # ------------------------------------------------------------------
    def _sigma(self, X: np.ndarray) -> np.ndarray:
        assert self.scaler is not None
        return ewma_sigma(
            X, self.scaler, self.sigma2_init, self.lam, self.return_channel
        )

    # ------------------------------------------------------------------
    def fit(self, dataset: Dataset, verbose: bool = False) -> "HybridEWMALSTM":
        cfg = self.cfg
        seed_everything(cfg.seed)
        device = cfg.resolve_device()

        self.scaler = dataset.scaler
        self.feature_scalers = getattr(dataset, "feature_scalers", None)
        self.return_channel = int(getattr(dataset, "return_channel", 0))
        self.horizon = dataset.horizon

        # EWMA tohumu: SADECE train. (baselines ile ayni.)
        r_train = dataset.scaler.inverse(dataset.y_train).ravel()
        self.sigma2_init = float(np.var(r_train))

        # --- hedefi standartlastir: u = r / sigma ---
        def prep(X, y):
            r = dataset.scaler.inverse(y)                 # (N, horizon) ham getiri
            s = self._sigma(X)[:, None]                   # (N, 1)
            return X.astype(np.float32), (r / s).astype(np.float32)

        Xtr, Utr = prep(dataset.X_train, dataset.y_train)
        Xva, Uva = prep(dataset.X_val, dataset.y_val)
        # TEST'e burada DOKUNULMAZ.

        net = QuantileLSTM(
            quantiles=cfg.quantiles,
            input_dim=Xtr.shape[-1],
            hidden_dim=cfg.hidden_dim,
            num_layers=cfg.num_layers,
            horizon=cfg.horizon,
            dropout=cfg.dropout,
        ).to(device)
        opt = torch.optim.Adam(
            net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay, foreach=False
        )

        def loader(X, U, shuffle):
            ds = TensorDataset(torch.as_tensor(X), torch.as_tensor(U))
            return DataLoader(ds, batch_size=cfg.batch_size, shuffle=shuffle,
                              num_workers=0)

        tr, va = loader(Xtr, Utr, True), loader(Xva, Uva, False)

        best_state, best_val, best_epoch, bad = None, float("inf"), -1, 0

        for epoch in range(1, cfg.max_epochs + 1):
            net.train()
            for xb, ub in tr:
                xb, ub = xb.to(device), ub.to(device)
                opt.zero_grad(set_to_none=True)
                loss = pinball_loss(net(xb), ub, cfg.quantiles)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), cfg.grad_clip)
                opt.step()

            net.eval()
            vs, vn = 0.0, 0
            with torch.no_grad():
                for xb, ub in va:
                    xb, ub = xb.to(device), ub.to(device)
                    loss = pinball_loss(net(xb), ub, cfg.quantiles)
                    vs += loss.item() * len(xb)
                    vn += len(xb)
            vl = vs / max(vn, 1)
            self.history.append({"epoch": epoch, "val_loss": vl})

            if vl < best_val - 1e-6:
                best_val, best_epoch, bad = vl, epoch, 0
                best_state = {k: v.detach().cpu().clone()
                              for k, v in net.state_dict().items()}
            else:
                bad += 1
            if bad >= cfg.patience:
                break

        if best_state is not None:
            net.load_state_dict(best_state)

        net.to("cpu")
        del opt, tr, va
        free_device_cache()

        self.net = net
        self.best_epoch = best_epoch
        self.best_val_loss = best_val
        if verbose:
            print(f"  [hybrid] en iyi epoch={best_epoch} val={best_val:.6f}")
        return self

    # ------------------------------------------------------------------
    @torch.no_grad()
    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        """(N, seq_len, F) -> (N, horizon, Q) LOG GETIRI uzayinda."""
        if self.net is None:
            raise RuntimeError("once fit() cagir")

        device = self.cfg.resolve_device()
        self.net.eval().to(device)

        x = torch.as_tensor(np.asarray(X_scaled, dtype=np.float32), device=device)
        q_u = self.net(x).cpu().numpy()               # (N, horizon, Q) standart uzay

        sigma = self._sigma(X_scaled)[:, None, None]  # (N, 1, 1)
        return q_u * sigma                            # -> log getiri
