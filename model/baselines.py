"""
Baseline modeller + tum modellerin paylastigi ARAYUZ.

Buradaki en onemli sey NaiveModel degil, ARAYUZUN KENDISI:

    fit(dataset) -> self
    predict(X_scaled) -> (N, horizon, Q)  **LOG GETIRI UZAYINDA**

Dikkat: predict'in cikisi OLCEKLENMIS DEGIL, ham log getiridir.
Sinir agi ici ic dunyasinda olcekli calisir ama sinirda inverse eder.
Sebep bir tuzak:

    "getiri = 0" demek, olcekli uzayda 0 demek DEGILDIR.
    z = (r - mean) / std  =>  r = 0  ==>  z = -mean / std  != 0

Naive'i olcekli uzayda 0 sanip oylece kiyaslarsan naive'e olmadigi bir
sapma yukler, model haksiz yere iyi gorunur. SinirI predict()'te cizdigimiz
icin metrics.py hic scaler gormez ve bu hatayi yapmasi IMKANSIZDIR.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from statistics import NormalDist

import numpy as np

from data.dataset import Dataset, Scaler


# --------------------------------------------------------------- arayuz
class QuantileForecaster(ABC):
    """Naive'den LSTM'e kadar her modelin uymak zorunda oldugu sozlesme."""

    name: str = "?"
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)

    @abstractmethod
    def fit(self, dataset: Dataset) -> "QuantileForecaster":
        ...

    @abstractmethod
    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        """
        Args:
            X_scaled: (N, seq_len, 1) -- OLCEKLENMIS log getiri pencereleri
        Doner:
            (N, horizon, Q) -- LOG GETIRI uzayinda quantile tahminleri
        """
        ...

    # -- yardimci --
    @property
    def median_idx(self) -> int:
        return self.quantiles.index(0.5)

    def _z(self) -> np.ndarray:
        """Standart normal quantile katsayilari. scipy gerekmez (stdlib)."""
        nd = NormalDist()
        return np.array([nd.inv_cdf(q) for q in self.quantiles], dtype=np.float64)


# ----------------------------------------------------------------- naive
class NaiveModel(QuantileForecaster):
    """
    Random walk: "yarinki log getiri = 0".

    GECILMESI GEREKEN CIZGI. Etkin piyasa hipotezinin en kaba hali ve
    gunluk tek degiskenli tahminde yenilmesi sasirtici derecede zordur.
    Bir model bunun RMSE'sinin altina inemiyorsa o model YOKTUR --
    RMSE'si ne kadar kucuk gorunurse gorunsun.

    Olasiliksal olarak dejenere: tum quantile'lar 0, aralik genisligi 0,
    kapsama ~0. Yani "risk" konusunda hicbir sey soylemez. RMSE/yon icin
    referanstir; belirsizlik icin rakip EWMA'dir.
    """

    name = "naive (r=0)"

    def __init__(self, quantiles: tuple[float, ...] = (0.1, 0.5, 0.9), horizon: int = 1):
        self.quantiles = tuple(quantiles)
        self.horizon = horizon

    def fit(self, dataset: Dataset) -> "NaiveModel":
        self.horizon = dataset.horizon
        return self  # ogrenecek bir sey yok -- olayin guzelligi da bu

    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        n = len(X_scaled)
        return np.zeros((n, self.horizon, len(self.quantiles)), dtype=np.float64)


# ------------------------------------------------------- sabit gaussian
class ConstantGaussianModel(QuantileForecaster):
    """
    Kosulsuz normal: r ~ N(mu_train, sigma_train).

    Gecmise bakmaz, pencereye bakmaz -- her gun ayni araligi verir.
    Isi: EWMA icin kontrol grubu olmak. EWMA bunu kapsama/pinball'da
    yenemiyorsa "oynaklik kumelenmesi" diye bir sey yakalanmiyor demektir.
    """

    name = "const gaussian"

    def __init__(self, quantiles: tuple[float, ...] = (0.1, 0.5, 0.9)):
        self.quantiles = tuple(quantiles)
        self.mu: float = 0.0
        self.sigma: float = 0.0
        self.horizon: int = 1

    def fit(self, dataset: Dataset) -> "ConstantGaussianModel":
        # SADECE train dilimi. y_train olcekli -> ham getiriye cevir.
        r_train = dataset.scaler.inverse(dataset.y_train).ravel()
        self.mu = float(np.mean(r_train))
        self.sigma = float(np.std(r_train))
        self.horizon = dataset.horizon
        return self

    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        n = len(X_scaled)
        q = self.mu + self._z() * self.sigma          # (Q,)
        return np.tile(q, (n, self.horizon, 1))       # (N, horizon, Q)


# -------------------------------------------------------------- EWMA vol
class EWMAVolModel(QuantileForecaster):
    """
    RiskMetrics EWMA oynaklik modeli:

        sigma^2_t = lam * sigma^2_{t-1} + (1 - lam) * r^2_{t-1}

    Medyan 0 (random walk -- getirinin ORTALAMASI tahmin edilmez),
    ama ARALIK her gun degisir: son gunler dalgaliysa aralik genisler.

    NEDEN ARIMA DEGIL DE BU:
      Gunluk getiride tahmin edilebilir olan ortalama degil OYNAKLIKTIR
      (volatility clustering -- Mandelbrot). ARIMA ortalamayi kovalar ve
      pratikte 0'a yakinsar; yani naive'in pahali bir kopyasi olur.
      Bizim modelimiz bir DAGILIM uretiyor, dolayisiyla dogru rakip da
      dagilim ureten klasik modeldir. LSTM'in araligi EWMA'nin araligindan
      daha bilgili degilse, sinir aginin katkisi sifirdir.

    lam = 0.94: RiskMetrics'in gunluk seriler icin standart degeri.
    """

    name = "EWMA vol (lam=0.94)"

    def __init__(
        self,
        quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
        lam: float = 0.94,
        drift: bool = False,
    ):
        if not 0.0 < lam < 1.0:
            raise ValueError(f"lam (0,1) araliginda olmali: {lam}")
        self.quantiles = tuple(quantiles)
        self.lam = lam
        self.drift = drift  # True -> medyan = train ortalamasi, False -> 0
        self.name = f"EWMA vol (lam={lam})"

        self._scaler: Scaler | None = None
        self.sigma2_init: float = 0.0
        self.mu: float = 0.0
        self.horizon: int = 1
        self.return_channel: int = 0

    def fit(self, dataset: Dataset) -> "EWMAVolModel":
        r_train = dataset.scaler.inverse(dataset.y_train).ravel()
        # EWMA'yi baslatmak icin tohum: train varyansi.
        self.sigma2_init = float(np.var(r_train))
        self.mu = float(np.mean(r_train)) if self.drift else 0.0
        self._scaler = dataset.scaler
        self.horizon = dataset.horizon
        # Cok degiskenli girdide X'in son ekseni F kanaldir; log getiri
        # bunlardan sadece BIRIDIR. Yanlis kanali ham getiri sanip EWMA'ya
        # sokmak (ornegin hacmi) modeli patlatmaz -- SESSIZCE sacmalatir.
        # MultiDataset bunu bildirir; klasik Dataset'te tek kanal vardir.
        self.return_channel = int(getattr(dataset, "return_channel", 0))
        return self

    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        if self._scaler is None:
            raise RuntimeError("once fit() cagir")

        # SADECE getiri kanalini al ve HAM getiriye cevir: (N, seq_len)
        # dataset.scaler, 0. kanalin (r) scaler'idir -- ayni nesne.
        x = np.asarray(X_scaled, dtype=np.float64)[..., self.return_channel]
        r = self._scaler.inverse(x)
        n, seq_len = r.shape

        # Her pencere icin EWMA'yi train varyansindan baslatip ileri sar.
        # Vektorlestirilmis: tum pencereler ayni anda ilerler.
        sigma2 = np.full(n, self.sigma2_init, dtype=np.float64)
        for t in range(seq_len):
            sigma2 = self.lam * sigma2 + (1.0 - self.lam) * r[:, t] ** 2

        sigma = np.sqrt(sigma2)                                # (N,)
        # (N, 1) * (Q,) -> (N, Q)
        q = self.mu + sigma[:, None] * self._z()[None, :]

        # horizon > 1: EWMA tek adim ilerisi icin ayni sigmayi verir
        # (getiriler bagimsiz varsayimi). Her ufka ayni aralik yayilir.
        return np.repeat(q[:, None, :], self.horizon, axis=1)   # (N, horizon, Q)


# ---------------------------------------------------------------- fabrika
def default_baselines(
    quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
    ewma_lambda: float = 0.94,
) -> list[QuantileForecaster]:
    """
    Her degerlendirmede bulunmasi gereken taban kume.
    NaiveModel HER ZAMAN listenin basindadir -- cikarilamaz.
    """
    return [
        NaiveModel(quantiles),
        ConstantGaussianModel(quantiles),
        EWMAVolModel(quantiles, lam=ewma_lambda),
    ]
