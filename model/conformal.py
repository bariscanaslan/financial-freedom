"""
Conformalized Quantile Regression (CQR) -- kapsama GARANTISI.

SORUN (holdout'ta olctuk):
    LSTM kapsamasi 0.755  -> hedefin ALTINDA. Riski KUCUK gosteriyor.
    EWMA kapsamasi 0.822  -> hedefin ustunde. Aralik gereksiz genis.

  Ikisi de kalibre degil. Bir risk urununde bu, nokta tahmininin
  kotu olmasindan DAHA ONEMLI bir kusurdur: "%80 ihtimalle bu araliktayiz"
  diyorsan ve gercek oran %75 ise, kullaniciya korunmadigi bir yerde
  korundugunu soylemis olursun.

COZUM (Romano, Patterson & Candes 2019):
  Modelin ham aralik tahminini, KALIBRASYON dilimindeki hatalarina bakarak
  simetrik bir miktar kadar genislet/daralt.

    E_i = max( q_lo(x_i) - y_i ,  y_i - q_hi(x_i) )     "uygunsuzluk skoru"

  E_i > 0  ise gercek deger araligin DISINDA kalmis (ne kadar disinda),
  E_i < 0  ise ICINDE (sinira ne kadar mesafeyle).

  Sonra E'nin (1-alpha) ampirik quantile'ini al ve araligi o kadar ac:

    [ q_lo - Q ,  q_hi + Q ]

  TEORIK GARANTI: veri degistirilebilir (exchangeable) ise kapsama
  >= 1 - alpha olur. MODELDEN BAGIMSIZ -- model ne kadar kotu olursa olsun
  kapsama tutar (kotu modelde aralik cok genisler, bedeli budur).

ZAMAN SERISINDE UYARI:
  Getiriler tam anlamiyla exchangeable DEGILDIR (oynaklik kumelenir).
  Garanti bu yuzden yaklasiktir, kesin degil. Pratikte cok iyi calisir ama
  "matematiksel olarak garantili" diye satma -- oynaklik rejimi degisirse
  kalibrasyon dilimi bayatlar. Periyodik yeniden kalibrasyon gerekir.

KALIBRASYON DILIMI = VAL. Test ASLA kullanilmaz -- kullanilirsa kapsama
"garantisi" test'e bakarak uydurulmus olur ve hicbir sey ifade etmez.
"""
from __future__ import annotations

import numpy as np

from data.dataset import Dataset

from .baselines import QuantileForecaster


class ConformalWrapper(QuantileForecaster):
    """
    Herhangi bir QuantileForecaster'i sarar ve kapsamasini duzeltir.

    Ic modele hic dokunmaz -- sadece cikan araligi kaydirir. Bu yuzden
    NaiveModel disinda her seyle calisir (naive'in araligi sifir genislikte
    oldugu icin conformal onu sabit genislikte bir araliga cevirir; anlamli
    ama ilginc degil).
    """

    def __init__(self, base: QuantileForecaster, alpha: float | None = None):
        """
        Args:
            base:  sarilacak model (fit EDILMIS olmali degil -- fit burada
                   zincirlenir)
            alpha: hedef hata orani. None -> base'in quantile'larindan
                   turetilir: (0.1, 0.5, 0.9) -> alpha = 0.2 (kapsama %80)
        """
        self.base = base
        self.quantiles = tuple(base.quantiles)
        self.alpha = (
            alpha if alpha is not None
            else 1.0 - (self.quantiles[-1] - self.quantiles[0])
        )
        self.q_adjust: float = 0.0
        self.name = f"{base.name} + conformal"

    # ------------------------------------------------------------------
    def fit(self, dataset: Dataset) -> "ConformalWrapper":
        # 1) ic modeli egit (train dilimi)
        self.base.fit(dataset)

        # 2) KALIBRASYON: VAL dilimi. TEST'E DOKUNULMAZ.
        pred = self.base.predict(dataset.X_val)        # (N, horizon, Q)
        y = dataset.scaler.inverse(dataset.y_val)      # (N, horizon)

        lo, hi = pred[..., 0], pred[..., -1]

        # uygunsuzluk skoru: araligin disinda kalma miktari (isaretli)
        E = np.maximum(lo - y, y - hi).ravel()
        n = len(E)

        # sonlu ornek duzeltmesi: ceil((n+1)(1-alpha)) / n
        # (+1 conformal'in kucuk ornekte de garanti vermesini saglar)
        level = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n)
        self.q_adjust = float(np.quantile(E, level, method="higher"))

        return self

    # ------------------------------------------------------------------
    def predict(self, X_scaled: np.ndarray) -> np.ndarray:
        pred = self.base.predict(X_scaled).copy()

        # Sadece en DIS quantile ciftini kaydir. Medyan ve aradakiler
        # oldugu gibi kalir -- nokta tahminini bozmuyoruz.
        pred[..., 0] -= self.q_adjust
        pred[..., -1] += self.q_adjust

        # q_adjust negatif olabilir (model asiri temkinliyse aralik DARALIR).
        # Bu durumda siralamanin bozulmadigindan emin ol: p10 < p50 < p90.
        med = pred[..., self.median_idx]
        pred[..., 0] = np.minimum(pred[..., 0], med)
        pred[..., -1] = np.maximum(pred[..., -1], med)

        return pred
