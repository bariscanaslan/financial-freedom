"""
Model katmani konfigurasyonu.

Tek bir ModelConfig nesnesi egitimi tam olarak tanimlar. Bu nesne
registry tarafindan modelle BIRLIKTE kaydedilir; boylece bir modeli
uretimde gorup "bu hangi ayarlarla egitilmisti?" diye sormak zorunda
kalmayiz.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import torch

from .device import free_cache, select_device

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------- device
# Cihaz mantigi model/device.py'de. Burasi sadece ince bir kabuk --
# boylece "hangi cihaz" sorusunun TEK bir dogru cevap yeri olur.
def get_device(prefer: str | None = None, *, ask: bool = False) -> torch.device:
    """
    Cihaz secimi: cuda > xpu > mps > cpu (makinede ne varsa).

    prefer verilirse ona saygi duyulur ("cpu", "cuda:1", "auto"...).
    ask=True ise VE gercek bir terminal varsa kullaniciya sorar; notebook,
    test ve sunucu sureclerinde bu bayrak sessizce yok sayilir (bkz. device.py).
    """
    return select_device(prefer, ask=ask)


def free_device_cache() -> None:
    """Hizlandirici bellegini birak. Cihaz turune gore dogru cagriyi yapar."""
    free_cache()


# ------------------------------------------------------------------- config
@dataclass
class ModelConfig:
    """
    Hiperparametreler.

    quantiles: SIRALI olmali ve 0.5'i ICERMELI.
      - 0.5 medyan = nokta tahmini (RMSE/MAE burada olculur)
      - uc/alt quantile'lar arasindaki genislik = RISK SINYALI
        (p90 - p10 genisse model "bilmiyorum" diyor demektir)
    """

    # --- veri sekli (Dataset ile tutarli olmali) ---
    seq_len: int = 30
    horizon: int = 1
    # Girdi kanal sayisi. 1 = tek degiskenli (sadece log getiri).
    # >1 = model/features.py'nin urettigi cok degiskenli girdi.
    input_dim: int = 1
    # Hangi ozellikler kullanildi -- registry'ye yazilir ki predict()
    # uretimde AYNI ozellikleri AYNI sirada yeniden kurabilsin.
    # Sira degisirse model sessizce yanlis calisir (patlamaz!).
    feature_names: tuple[str, ...] = ("r",)

    # --- olasiliksal cikti ---
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)

    # --- mimari ---
    hidden_dim: int = 64
    num_layers: int = 2
    dropout: float = 0.2  # num_layers > 1 ise LSTM katmanlari arasinda

    # --- optimizasyon ---
    lr: float = 1e-3
    weight_decay: float = 1e-5
    batch_size: int = 64  # minibatch. full-batch DEGIL.
    max_epochs: int = 200
    patience: int = 15  # early stopping: VAL uzerinde, test'e bakilmaz
    grad_clip: float = 1.0  # LSTM'de patlayan gradyan sigortasi

    # --- tekrarlanabilirlik ---
    seed: int = 42
    # None  -> cihaz CALISMA ANINDA coozulur (device.py'nin secim sirasi:
    #          acik deger > SPP_DEVICE > oturumda secilen > otomatik).
    #          Modeli CUDA'li makinede egitip XPU'lu makinede yuklemek
    #          bu sayede sorunsuz calisir -- cfg'ye cihaz CIVILENMEZ.
    # "cpu"  -> zorla. Testlerde determinizm, coklu supurmede kararlilik icin.
    device: str | None = None

    # --- klasik baseline ---
    ewma_lambda: float = 0.94  # RiskMetrics standardi (gunluk seri)

    def __post_init__(self) -> None:
        q = tuple(float(x) for x in self.quantiles)
        if list(q) != sorted(q):
            raise ValueError(f"quantiles sirali olmali: {q}")
        if len(set(q)) != len(q):
            raise ValueError(f"quantiles tekrarli: {q}")
        if not all(0.0 < x < 1.0 for x in q):
            raise ValueError(f"quantiles (0,1) araliginda olmali: {q}")
        if 0.5 not in q:
            # Medyan olmadan nokta tahmini ve yon dogrulugu tanimsiz kalir.
            raise ValueError(f"quantiles 0.5 (medyan) icermeli: {q}")
        self.quantiles = q

        self.feature_names = tuple(self.feature_names)
        if len(self.feature_names) != self.input_dim:
            raise ValueError(
                f"input_dim={self.input_dim} ile feature_names "
                f"({len(self.feature_names)} adet) uyusmuyor"
            )
        if self.feature_names[0] != "r":
            raise ValueError("0. kanal 'r' (log getiri) olmali")

    # -- turetilmisler --
    @property
    def n_quantiles(self) -> int:
        return len(self.quantiles)

    @property
    def median_idx(self) -> int:
        """0.5'in quantiles icindeki indeksi. Head bunu cipa alir."""
        return self.quantiles.index(0.5)

    @property
    def nominal_coverage(self) -> float:
        """En dis quantile ciftinin teorik kapsama orani. (0.1, 0.9) -> 0.80"""
        return self.quantiles[-1] - self.quantiles[0]

    def resolve_device(self) -> torch.device:
        """
        Egitim/tahmin aninda kullanilacak cihaz. ASLA soru sormaz --
        egitim dongusunun ortasinda input() beklemek kabul edilemez.
        Soru, varsa, script basinda bir kez sorulur (device.select_device).
        """
        return get_device(self.device, ask=False)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["quantiles"] = list(self.quantiles)
        d["feature_names"] = list(self.feature_names)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ModelConfig":
        d = dict(d)
        d["quantiles"] = tuple(d["quantiles"])
        d["feature_names"] = tuple(d.get("feature_names", ("r",)))
        return cls(**d)
