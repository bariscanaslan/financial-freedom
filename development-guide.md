# Development Guide — Stock Price Predictor

Bu dosya kodun **ne yaptığını** anlatmaz; kod zaten onu anlatıyor. Bu dosya
**neden böyle yaptığını** ve **neyin denenip başarısız olduğunu** anlatır.

İkincisi daha önemli. Bu projede üç ayrı yaklaşım denendi ve üçü de aynı
duvara çarptı. Bunu bilmeyen biri aynı üç yolu baştan yürür. Aşağıdaki
"Denendi, olmadı" bölümü bu yüzden var — orayı okumadan yeni model yazma.

> **Bu bir yatırım tavsiyesi ürünü değildir.** Amaç: tahmin + belirsizlik
> ölçümü. Aşağıdaki kuralların çoğu bu cümleyi savunmak için var.

---

## 1. Değişmez kurallar

Bunlar tercih değil. İhlal edilirse ürün sessizce yalan söyler — patlamaz,
sadece yanlış olur. En kötü hata türü budur.

### 1.1 Leakage yok
- Scaler **sadece train dilimine** fit edilir. Önce split, sonra ölçekleme.
- Pencereler **her dilim içinde ayrı** üretilir. Hiçbir pencere dilim
  sınırını aşmaz.
- Kronolojik split. **Shuffle yok.** (Minibatch içinde pencerelerin görülme
  sırası karışabilir — bu leakage değil; her pencere kendi dilimi içinde
  kapalı bir örnektir.)
- `registry.load()` scaler'ı **diskten okur, yeniden fit etmez.** Yeniden fit
  etmek üretim verisine fit etmektir; leakage'ın arka kapıdan dönüşü.

### 1.2 Hedef = log getiri, fiyat seviyesi değil
Seviye tahmininde model "dünkü fiyatı kopyala" çözümünü bulur. RMSE mükemmel
görünür, bilgi değeri sıfırdır. **RMSE'yi güzel göstermek için hedefi fiyata
geri çevirme.** Fiyat sadece bir *sunum* çevirisidir:

    P_t = anchor_price * exp(r_t)      # anchor = hedef günden bir önceki kapanış

`metrics.price_rmse` bu yüzden docstring'inde "kıyas için değil" diye
uyarıyor — fiyat RMSE'si her zaman iyi görünür.

### 1.3 Naive baseline kutsal
`naive = "yarınki getiri 0"` (random walk). Her metrik raporunda **zorunlu**.
`evaluate()` naive'i listeden çıkarsan bile geri koyar.

    skill_score = 1 - rmse_model / rmse_naive

- `> MIN_SKILL (0.01)` → model naive'i **anlamlı** ölçüde yendi
- `0 < skill <= 0.01` → **gürültü.** Kazanç değil. Test dilimini birkaç gün
  kaydırsan işareti değişir. Buna "yendi" **denmez**.
- `<= 0` → model yok.

RMSE'nin küçük görünmesi tek başına hiçbir şey ifade etmez. Günlük log
getiriler zaten ~0.02 büyüklüğündedir.

### 1.4 Çıktı bir dağılım, tek sayı değil
Nokta tahmini (ŷ = 187.32) risk taşımaz. Model p10/p50/p90 üretir.
**Risk sinyali = p90 − p10.** Sentiment risk katmanı ileride bunun *üstüne*
oturacak, yerine değil.

Quantile crossing (p10 > p50) **cezalandırılmaz, yapısal olarak imkânsız
kılınır** (`nets.py`, medyan çıpası + kümülatif softplus). Loss'un iyi
niyetine bırakılmış bir şey değil — 50 sigma girdide bile sıralı çıkar.

### 1.5 predict() sınırı: log getiri uzayı
**Bütün** modeller (naive dahil) `predict()`'ten **log getiri** döndürür.
Scaler modelin *içinde* yaşar. Sebebi bir tuzak:

    "getiri = 0" demek ölçekli uzayda 0 demek DEĞİLDİR.
    z = (r - mean)/std  =>  r = 0  ==>  z = -mean/std  ≠ 0

Bu karışsaydı naive'e olmayan bir sapma yüklenir, model haksız yere iyi
görünürdü. Sınırı `predict()`'te çizdiğimiz için `metrics.py` hiç scaler
görmez ve bu hatayı yapması imkânsızdır. **Bu sınırı taşıma.**

---

## 2. Dürüst değerlendirme protokolü

Kurallardan daha zor olan kısım. `data/` katmanında scaler'ı test'e fit
etmeyi yasakladık; burada da **mimariyi** test'e fit etmemek gerekiyor.

### Test setine bakma bütçesi vardır ve harcanır
- Bütün iterasyon (özellik seçimi, mimari, hiperparametre) **VAL** üzerinde.
- TEST'e **bir kez**, en sonda, tek konfigürasyonla bakılır.
- Sonuç kötü çıkarsa geri dönüp başka bir şey deneyip **aynı test setine**
  tekrar bakmak yasak. O an test kirlenir; raporladığın skor artık modelin
  değil, **kaç kez baktığının** fonksiyonudur.

### Temiz holdout
Dev ticker'ların (`AAPL/MSFT/NVDA/KO`) TEST dilimine zaten bakıldı. Yeni bir
mimari kararı verecekseniz **hiç görülmemiş ticker'larda** ölçün
(`tests/run_hybrid.py` bunu yapıyor: 8 yeni hisse). Bu ayrıca daha zor bir
sınavdır — model yeni bir *zamana* değil, yeni bir *hisseye* genellemek
zorundadır.

### İstatistiksel anlamlılık zorunlu
"Ortalama %1 daha iyi" bir sonuç değildir. Eşli t-testi yap (örnek başına
pinball farkı). `p >= 0.05` ise **fark yoktur**, ne kadar cazip görünürse
görünsün. `tests/run_hybrid.py` bunu havuzlanmış olarak hesaplıyor.

### Kırmızı bayrak
Sentetik GBM verisinde (`tests/smoke_gbm.py`) model naive'i yenerse bu **iyi
haber değil, leakage haberidir.** GBM'de tanım gereği sinyal yoktur. Smoke
test bu beklentiyle yazılmıştır: `skill < 0.05` bekler.

---

## 3. Denendi, olmadı — tekrar deneme

Bu bölüm bu projenin en değerli kısmı. Hepsi ölçüldü, tahmin edilmedi.

| Yaklaşım | Ne yapıldı | Sonuç |
|---|---|---|
| **Tek değişkenli QuantileLSTM** | 30 günlük log getiri → p10/p50/p90 | skill_score −0.003…+0.006, 4 ticker'da 0/4. **Naive yenilmedi.** |
| **Özellik zenginleştirme** | +oynaklık ailesi (abs_r, rv_5, rv_21, Parkinson, rv_ratio), momentum, hacim, SPY piyasa faktörü, göreli güç → 9 kanal | VAL'de tek değişkenli +%1.66, 9 özellikli +%1.77. **Dokuz özelliğin katkısı %0.1.** TEST'te sıfır. |
| **EWMA-çıpalı hibrit** | Hedefi EWMA sigma'sına bölüp modele oynaklık seviyesini bedava ver (`hybrid.py`) | VAL'de +%1.85 — düz LSTM ile **aynı**. Fark yok. |
| **Temiz holdout doğrulaması** | 8 görülmemiş hisse, n=3216, eşli t-testi | pinball ortalama **−%0.21**, havuzlanmış **p=0.86**. Anlamlı: 0/8. |

**Sonuç: günlük getiri verisinde sinir ağının EWMA'ya katacağı bilgi yok.**

VAL'de tutarlı görünen +%1.85'lik kazanç, görülmemiş hisselerde tamamen
buharlaştı. O kazanç modelin değil, dev ticker'larının VAL rejimine oturmuş
olmanın eseriydi.

### Bundan çıkan kural
> **Dördüncü mimariyi deneme.** Yeterince mimari denersen biri holdout'ta
> şansa geçer, ve o "sonuç" sahte olur. Cevabı değiştirecek olan şey yeni
> mimari değil, **yeni bilgi**dir.

Üretimde şu an **EWMA + conformal** kullanılmalı: en iyi kalibre (sapma
0.020) ve en iyi pinball. Üç satırlık, eğitimsiz, denetlenebilir. LSTM
registry'de "yenmesi gereken aday" olarak durur — altyapı hazır, yeni bir
bilgi kaynağı geldiğinde tek satırla yarışa girer.

### Kalibrasyon: bilinen kusur
Conformal (`conformal.py`) EWMA'yı düzeltti (0.822 → 0.780) ama **LSTM'i
kurtaramadı** (0.755 → 0.763, hâlâ dar). Sebep teoride yazılıydı: conformal'ın
garantisi verinin *değiştirilebilir* (exchangeable) olmasına dayanır;
getiriler oynaklık kümelenmesi yüzünden değildir. Rejim kayarsa kalibrasyon
dilimi bayatlar. **Periyodik yeniden kalibrasyon gerekir.**

Kapsamanın **hedefin altında** olması, üstünde olmasından tehlikelidir:
kullanıcıya korunmadığı bir yerde korunduğunu söylersin.

---

## 4. Katman haritası

```
data/        TAMAMLANDI — DEĞİŞTİRME
  config.py     yollar, sabitler (CACHE_DIR, MIN_BARS, OHLCV_COLS)
  loader.py     fetch/fetch_many, normalize OHLCV, parquet cache, retry
  validate.py   validate(df) -> Report (NaN, high<low, split hatası…)
  calendar.py   işlem günü hizalama
  dataset.py    build_dataset() -> Dataset. Scaler, log_returns, naive_baseline

model/       TAMAMLANDI
  device.py     cihaz seçimi: cuda > xpu > mps > cpu  (§5)
  config.py     ModelConfig — hiperparametreler + input_dim + feature_names
  nets.py       QuantileLSTM — crossing yapısal olarak imkânsız
  losses.py     pinball_loss (torch + numpy)
  features.py   build_multi_dataset() — çok kanallı, aynı leakage disiplini
  baselines.py  QuantileForecaster ARAYÜZÜ + Naive / ConstantGaussian / EWMAVol
  hybrid.py     HybridEWMALSTM — EWMA çıpalı (denendi, katkı yok)
  conformal.py  ConformalWrapper — kapsama kalibrasyonu (VAL'de)
  metrics.py    rmse/mae/pinball/coverage/dir_acc/skill_score
  train.py      minibatch, early stopping (VAL), seed, test'e dokunmaz
  registry.py   save/load — scaler MODELLE BİRLİKTE
  evaluate.py   tüm modeller yan yana; naive her zaman tabloda
  predict.py    predict(model_path, recent_df) -> {p10,p50,p90} getiri + fiyat

sentiment/   SONRAKİ ADIM — finbert, ayrı risk katmanı
portfolio/   sonra — event log, actual vs simulated
api/         sonra — FastAPI (predict.py'yi çağıracak)
ui/          sonra
```

### Model arayüzü
Yeni bir model eklerken `QuantileForecaster`'ı uygula — o zaman `evaluate()`
tablosuna ücretsiz girer ve naive ile kıyaslanır:

```python
fit(dataset) -> self
predict(X_scaled) -> (N, horizon, Q)   # LOG GETİRİ uzayında
```

---

## 5. Cihaz katmanı

Kodun hiçbir yerinde elle `"xpu"` yazma. `model/device.py` makinede ne varsa
onu bulur: **cuda > xpu > mps > cpu**.

Çözüm sırası (üstteki kazanır):
1. Açık değer — `select_device("cuda:1")`
2. Ortam değişkeni — `SPP_DEVICE=cpu python tests/run_hybrid.py`
3. Oturumda daha önce seçilmiş olan
4. İnteraktif soru — **yalnızca `ask=True` ise ve gerçek terminal varsa**
5. Otomatik

Script bazlı çalışmaya geçince, soruyu **main()'in ilk satırında** sor:

```python
from model.device import select_device
select_device(ask=True)     # bir kez sorulur, oturum boyunca hatırlanır
```

**Kütüphane import'unda asla `input()` çağırma.** Bu paket notebook'ta,
pytest'te, cron'da ve ileride FastAPI sürecinde import edilecek — hiçbirinde
stdin yok. Import anında soru soran modül sunucuyu kilitler; hata bile
vermez, sadece asılı kalır. `_is_interactive()` bunu engelliyor.

Olmayan cihaz istenirse **hata verilir, sessizce CPU'ya düşülmez.** Sessizce
düşseydi kullanıcı GPU'da eğittiğini sanıp saatlerce CPU'da beklerdi.
Otomatik isteyen `"auto"` yazar.

`ModelConfig.device` varsayılan `None` → cihaz **çalışma anında** çözülür.
Bu sayede CUDA'lı makinede eğitilen model XPU'lu makinede yüklenip çalışır;
cihaz `meta.json`'a çivilenmez.

### Bilinen altyapı sorunu: torch 2.13.0+xpu
Ard arda ~20 model eğitilince `UR_RESULT_ERROR_OUT_OF_RESOURCES` ile çöküyor.
Alınan önlemler: `Adam(foreach=False)` + eğitim sonrası ağı CPU'ya alıp
`free_cache()`. Bu **iyileştirdi ama tam çözmedi** — süreç başına sızan bir
kaynak var. Bu yüzden çoklu süpürme koşuları (`run_hybrid.py`,
`run_conformal.py`) `DEVICE = "cpu"` ile çalışıyor. **Tek model eğitiminde
XPU sorunsuz.** Modeller küçük (~50k parametre), CPU rahat kaldırıyor.

---

## 6. Testler

```bash
.venv/Scripts/python.exe tests/smoke_gbm.py       # sentetik GBM — HER DEĞİŞİKLİKTEN SONRA
.venv/Scripts/python.exe tests/run_real.py        # gerçek veri, tek model
.venv/Scripts/python.exe tests/run_enriched.py    # özellik seti yarışması (VAL)
.venv/Scripts/python.exe tests/run_hybrid.py      # temiz holdout protokolü
.venv/Scripts/python.exe tests/run_conformal.py   # kapsama kalibrasyonu
```

`smoke_gbm.py` regresyon kalkanıdır: leakage, quantile crossing, scaler
kaydı/yüklemesi, fiyat çevirisi ve `predict()` yolunu ağsız kontrol eder.
Model katmanına dokunduysan **önce bunu çalıştır.**

---

## 7. Sıradaki adım: sentiment

Bugünkü sonuç sentiment katmanının değerini **artırıyor** — çünkü artık
"LSTM zaten hallediyordu" diyemeyiz. Fiyat serisinin içinde olmayan bir
sinyal getiren tek şey o.

Eklerken:
- **Ayrı bir risk katmanı** olarak ekle, fiyat modelinin girdisine karıştırma.
  (Ürün kararı — plan böyle.)
- **Nedensellik:** t günü kapanışında gerçekten bilinen haberi kullan.
  Haberin *yayın zaman damgası* kritik. Gün sonunda yayınlanan bir haberi
  o günün özelliği yapmak leakage'dır ve modeli sahte şekilde parlatır.
- Aynı dürüst protokol geçerli: VAL'de geliştir, temiz holdout'ta karar ver,
  eşli t-testi yap, naive'i tabloda tut.

---

## 8. Hızlı kontrol listesi (PR öncesi)

- [ ] `tests/smoke_gbm.py` geçiyor mu?
- [ ] Yeni bir metrik/model eklediysen naive tabloda mı?
- [ ] Test setine kaç kez baktın? Birden fazlaysa sonucu böyle raporla.
- [ ] Skill score pozitif ama < 0.01 mi? O zaman **"yendi" deme.**
- [ ] Yeni özellik eklediysen: *"Bu sayıyı t günü piyasa kapanırken gerçekten
      bilebilir miydim?"* Cevap hayırsa leakage.
- [ ] Kapsama hedefin **altında** mı? Bu, üstünde olmaktan tehlikelidir.
- [ ] Cihaz elle mi yazılmış? `device.py` kullan.
- [ ] Sonuç olumsuzsa **gizleme.** Bu projede olumsuz sonuç da sonuçtur.
