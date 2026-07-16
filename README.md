# Financial Freedom

Günlük hisse getirisi için **olasılıksal** tahmin motoru. Çıktı tek bir sayı
değil, bir dağılımdır: p10 / p50 / p90. Nokta tahmini medyandır (p50), risk
sinyali ise aralık genişliğidir (p90 − p10).

> **Bu bir yatırım tavsiyesi ürünü değildir.** Amaç: tahmin + belirsizlik
> ölçümü.

Bu dosya projenin **ne olduğunu ve nasıl çalıştığını** anlatır. Kararların
**neden** böyle alındığını ve **neyin denenip başarısız olduğunu**
`development-guide.md` anlatır — yeni bir model yazmadan önce orası okunmalı.

---

## Backend ve frontend'i çalıştırma

Önerilen yöntem tüm yapıyı Docker Compose ile çalıştırmaktır:

```bash
cp .env.example .env
docker compose up -d --build
```

Varsayılan imaj CPU ile çalışır. NVIDIA Container Toolkit kurulu bir makinede
CUDA ile eğitim/tahmin için GPU override'ını kullanın:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

Uygulama varsayılan olarak yalnızca bu makineden `http://127.0.0.1:3007`
adresinde açılır. Redis, API ve UI doğrudan dışarı port yayınlamaz; trafik Nginx
üzerinden geçer. VPN erişimi için `.env` içindeki `VPN_BIND_ADDRESS` değerini
sunucunun VPN arayüz IP'siyle değiştirin ve `http://<VPN_IP>:3007` adresini
kullanın. Servis durumlarını görmek için:

```bash
docker compose ps
docker compose logs -f
```

Veriler `cache/`, modeller `models/`, SQLite kayıtları `portfolio_data/`
dizinlerinde kalıcıdır. Container'ları durdurmak için `docker compose down`
kullanın.

Docker kullanmadan geliştirme yapmak için önce proje kökünde Python ve frontend
bağımlılıklarını kurun:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ui
npm install
cp .env.example .env.local
cd ..
```

Redis'i ayrı bir terminalde başlatın:

```bash
docker compose up -d redis
```

Varsayılan bağlantı `redis://127.0.0.1:6389/0` adresidir. Farklı bir adres için
`SPP_API_REDIS_URL` ortam değişkenini ayarlayın. Redis erişilemezse API mevcut
bellek ve Parquet önbelleğine otomatik döner; kalıcı portföy/tahmin/risk kayıtları
SQLite içinde kalır.

Backend'i proje kökünde başlatın:

```bash
.venv/bin/uvicorn api.main:app --reload --port 8089
```

API `http://127.0.0.1:8089` adresinde çalışır. Ardından ikinci bir terminalde
frontend'i başlatın:

```bash
cd ui
npm run dev
```

Web arayüzünü `http://localhost:3007` adresinden açabilirsiniz. Farklı bir API
adresi kullanacaksanız `ui/.env.local` içindeki `NEXT_PUBLIC_API_URL` değerini
güncelleyin.

---

## Şu anki durum

| Katman | Durum | Not |
|---|---|---|
| `data/` | Tamamlandı | OHLCV indirme, doğrulama, dataset üretimi. Değiştirilmiyor. |
| `model/` | Tamamlandı | Baseline'lar, LSTM, conformal, eğitim, değerlendirme, kayıt, tahmin. |
| `tests/` | Tamamlandı | Smoke + gerçek veri + holdout protokolü koşucuları. |
| `portfolio/` | Tamamlandı | Event log (tek gerçek kaynak), replay, değerleme, simülasyon, rapor. |
| `api/` | Tamamlandı | FastAPI; `predict.py` ve `portfolio/`'yu saran ince HTTP kabuğu. |
| `ui/` | Tamamlandı | Next.js; tahmin / portfolyo / risk / rehber sayfaları. |
| `sentiment/` | Başlamadı | Sıradaki adım — ayrı risk katmanı (FinBERT). |

**Temel bulgu (ölçümle vardık, tahminle değil):** Günlük tek değişkenli getiri
verisinde sinir ağı, naive (random walk) ve EWMA baseline'ını **anlamlı ölçüde
yenemiyor.** Üç ayrı mimari denendi, üçü de görülmemiş hisselerde sıfıra çöktü.
Bu yüzden üretim önerisi şu an **EWMA + conformal**'dır; LSTM registry'de
"yenilmesi gereken aday" olarak durur. Ayrıntı: `development-guide.md` §3.

Geliştirme şu ana kadar `Main.ipynb` üzerinde yürüdü; kod oradan bu modüler
yapıya taşındı.

---

## Kurulum ve ortam

- Python 3.14, `.venv` sanal ortamı.
- Bağımlılıklar `requirements.txt` içinde: `numpy`, `pandas`, `torch`,
  `yfinance`, `pyarrow` (parquet cache motoru).

```bash
.venv/bin/pip install -r requirements.txt
```

Cihaz (CUDA / XPU / CPU) elle yazılmaz; `model/device.py` makinede ne varsa
onu bulur. Seçim sırası: **cuda > xpu > mps > cpu**. Bu makinede hangi cihazın
seçileceğini görmek için: 

```bash
.venv/bin/python -m model.device
```

`ModelConfig.device` varsayılan `None`'dır → cihaz **çalışma anında** çözülür.
Böylece CUDA'lı makinede eğitilen model başka bir makinede sorunsuz yüklenir;
cihaz `meta.json`'a çivilenmez. Tek seferlik zorlamak için:
`SPP_DEVICE=cpu .venv/bin/python tests/run_real.py`.

---

## Katman haritası ve dosyalar

Aşağıda her modülün **ne yaptığı ve nasıl çalıştığı** var. Tasarım gerekçeleri
için ilgili dosyanın başındaki docstring'e ve `development-guide.md`'ye bakın.

### `data/` — veri katmanı (tamamlandı)

| Dosya | Görev |
|---|---|
| `config.py` | Yollar (`CACHE_DIR`), sabitler (`OHLCV_COLS`, `MIN_BARS`, `DEFAULT_START`). |
| `loader.py` | `fetch` / `fetch_many`: yfinance'ten OHLCV indirir, normalize eder, parquet cache'ler, retry yapar. |
| `calendar.py` | İşlem günü hizalaması (tz-naive borsa günü). |
| `validate.py` | `validate(df)` → rapor: NaN, `high < low`, split hatası vb. |
| `dataset.py` | **Kritik katman.** `build_dataset()`: ham OHLCV → model-hazır tensörler. |

`dataset.py` üç notebook hatasını burada çözer ve sırayı **bozmaz**:

1. **Leakage yok.** Önce kronolojik split (shuffle yok), *sonra* ölçekleme.
   Scaler yalnızca **train** dilimine fit edilir.
2. **Hedef = log getiri**, fiyat seviyesi değil. Seviye tahmininde model
   "dünkü fiyatı kopyala" çözümüne kaçar; RMSE güzel görünür, bilgi sıfırdır.
3. **Pencereler her dilim içinde ayrı** üretilir; hiçbir pencere dilim
   sınırını aşmaz.

`Scaler` da burada tanımlıdır (mean/std + neye fit edildiği). Modelle birlikte
diske yazılır, yükleme sırasında **yeniden fit edilmez** — yeniden fit,
leakage'ın arka kapıdan dönüşüdür.

### `model/` — model katmanı (tamamlandı)

| Dosya | Görev |
|---|---|
| `device.py` | Cihaz seçimi (cuda > xpu > mps > cpu). Import'ta asla soru sormaz. |
| `config.py` | `ModelConfig`: hiperparametreler + `input_dim` + `feature_names`. |
| `nets.py` | `QuantileLSTM`: quantile crossing yapısal olarak imkânsız. |
| `losses.py` | `pinball_loss` (torch + numpy). |
| `features.py` | `build_multi_dataset()`: çok kanallı girdi, aynı leakage disiplini. |
| `baselines.py` | `QuantileForecaster` arayüzü + Naive / ConstantGaussian / EWMAVol. |
| `hybrid.py` | `HybridEWMALSTM`: EWMA çıpalı model (denendi, katkı çıkmadı). |
| `conformal.py` | `ConformalWrapper`: kapsama kalibrasyonu (VAL üzerinde). |
| `metrics.py` | rmse / mae / pinball / coverage / dir_acc / skill_score. |
| `train.py` | Eğitim döngüsü + `TrainedModel`. Test'e dokunmaz. |
| `registry.py` | `save` / `load`. Scaler modelle **birlikte** kaydedilir. |
| `evaluate.py` | Tüm modeller yan yana; naive her zaman tabloda. |
| `predict.py` | `predict(model_path, recent_df)` → getiri + fiyat dağılımı. |

Öne çıkan yapılar:

- **`baselines.py` — ortak arayüz.** Naive'den LSTM'e kadar her model
  `QuantileForecaster` sözleşmesine uyar: `fit(dataset)` ve
  `predict(X_scaled) → (N, horizon, Q)`. `predict()` çıktısı **log getiri
  uzayındadır** (ölçekli değil). Yeni bir model bu arayüzü uygularsa
  `evaluate()` tablosuna otomatik girer ve naive ile kıyaslanır.

- **`nets.py` — crossing imkânsız.** Medyan serbest bırakılır; üstteki
  quantile'lar kümülatif `softplus` ile yukarı, alttakiler aşağı itilir.
  `softplus > 0` olduğu için p10 < p50 < p90 bir umut değil, cebirsel
  sonuçtur — kötü eğitimde bile bozulamaz.

- **`train.py` — dürüst eğitim.** Minibatch, sabit seed, early stopping
  **VAL** pinball loss'una göre. `dataset.X_test` bu dosyada hiç geçmez.
  En iyi VAL ağırlıkları geri yüklenir. `TrainedModel` ağı + scaler'ı + cfg'yi
  bir arada tutar.

- **`registry.py` — scaler modelle birlikte.** Disk düzeni:
  `models/<TICKER>_<zaman>/` içinde `model.pt` (yalnız state_dict) ve
  `meta.json` (scaler, cfg, metrikler, git commit — insan okunur). Yükleme
  scaler'ı diskten okur.

- **`evaluate.py` — naive kutsal.** Naive tabloya opsiyonel eklenmez, **her
  zaman** oradadır; çağıran çıkarsa geri konur. `skill_score = 1 −
  rmse_model / rmse_naive`. Eşik `MIN_SKILL = 0.01`: bunun altındaki pozitif
  skor kazanç değil, gürültüdür. Kimse naive'i yenmediyse tablonun altına
  susturulamayan bir uyarı basılır.

- **`conformal.py` — kapsama garantisi.** Herhangi bir modeli sarar, iç
  aralığı VAL dilimindeki hatalara bakarak genişletir/daraltır. **Test'e asla
  dokunmaz.**

- **`predict.py` — üretim sınırı.** Kaydedilmiş model + güncel OHLCV →
  `Forecast`. Burada eğitim, dataset kurulumu veya scaler fit'i **yoktur**;
  scaler diskten gelir. Çıktı hem log getiri hem fiyat olarak verilir; fiyat
  yalnızca bir sunum çevirisidir: `P = anchor * exp(r)`.

### `tests/` — koşucular

| Dosya | Görev |
|---|---|
| `smoke_gbm.py` | Sentetik GBM: leakage, crossing, scaler kayıt/yükleme, fiyat çevirisi, `predict()` yolunu ağsız kontrol eder. **Her değişiklikten sonra.** |
| `run_real.py` | Gerçek veri, tek model. |
| `run_enriched.py` | Özellik seti yarışması (VAL). |
| `run_hybrid.py` | Temiz holdout protokolü (görülmemiş hisseler, eşli t-testi). |
| `run_conformal.py` | Kapsama kalibrasyonu. |

```bash
.venv/bin/python tests/smoke_gbm.py
.venv/bin/python tests/run_real.py
```

`smoke_gbm.py` regresyon kalkanıdır. Model katmanına dokunduysan **önce onu
çalıştır.** GBM'de tanım gereği sinyal yoktur; model orada naive'i yenerse bu
iyi haber değil, **leakage haberidir.**

`smoke_api.py` ve `smoke_portfolio.py` ise API ve portfolyo katmanlarını ağsız
doğrular (girdi reddi, portfolyo izolasyonu, muhasebe kimliği, quantile
sırası). İkisi de dış ağ istemez.

### `portfolio/` — portfolyo katmanı (tamamlandı)

| Dosya | Görev |
|---|---|
| `config.py` | Yollar (`PORTFOLIO_DIR`) ve sabitler. Kişisel işlem verisi repoya girmez. |
| `events.py` | Event veri modeli — portfolyonun **tek gerçek kaynağı** (K1). |
| `store.py` | `EventStore`: append-only event log + parquet kalıcılığı. |
| `portfolio.py` | Event log'u **replay** ederek herhangi bir tarihte pozisyon + nakit. |
| `valuation.py` | İşlem günü takvimi boyunca mark-to-market değerleme. |
| `positions.py` | Per-pozisyon anlık görünüm + fiyat bazlı period değişimi (1g/1h/1a). |
| `metrics.py` | Performans metrikleri; **hepsi net-of-fees** (fee'ler event'lerde). |
| `simulate.py` | "Yatırım yapsaydım" senaryoları: alternatif event log, **aynı** valuation. |
| `report.py` | actual vs simulated vs benchmark tek tabloda (K4). |
| `forecast_link.py` | `model/predict.py`'nin `Forecast`'ini **portfolyo düzeyine** toplar. |

Öne çıkan yapı — **event log tek gerçek kaynak.** Pozisyon ve nakit hiçbir yerde
saklanmaz; her tarih için event log **baştan replay** edilir. Simülasyon gerçek
log'u değiştirmez, yalnızca alternatif bir log üretir ve aynı değerleme
yolundan geçirir. Fee'siz simülasyon **sistematik olarak iyimserdir** (K3) —
bu yüzden çıktılar bunu açıkça söyler. Korelasyon ihmal edilir (komonoton
varsayım): aralık **muhafazakâr/geniştir**, aksiyon önerisi değildir.

### `api/` — HTTP katmanı (tamamlandı)

| Dosya | Görev |
|---|---|
| `main.py` | FastAPI uygulaması; router'ları bağlar. |
| `config.py` | API ayarları (`pydantic-settings`, önek `SPP_API_`). |
| `schemas.py` | Pydantic request/response modelleri. **Girdi doğrulama burada.** |
| `deps.py` | Paylaşılan servisler + `portfolio_id` sınırı (enjeksiyon reddi). |
| `errors.py` | İstisna → temiz HTTP; iç detay (stack trace, dosya yolu) dışarı sızmaz. |
| `routers/predict.py` | `GET /models`, `POST /predict`. |
| `routers/portfolio.py` | `GET /{id}`, `/positions`, `/value`, `/metrics`, `/report`, `/forecast`; `POST /events`, `/simulate`. |
| `routers/health.py` | `GET /health`. |

API `model/` ve `portfolio/` üstünde **ince bir kabuktur** — iş mantığı içermez,
onları çağırır. Girdi doğrulama şemada yapılır; `model_path`/`portfolio_id`
enjeksiyonu ve geçersiz miktar/ticker **422** ile reddedilir.

### `ui/` — arayüz (tamamlandı)

Next.js (App Router) + TypeScript + vitest. Sayfalar: `predict` (tahmin bandı),
`portfolio` (pozisyon tablosu + değer kartı), `risk` (risk rozeti + korelasyon
uyarısı), `guide` (rehber). `lib/api.ts` API katmanını çağırır; `Disclaimer`
ve uyarı bileşenleri "yatırım tavsiyesi değildir" sınırını her ekranda tutar.

---

## Uçtan uca akış

```
data/loader.fetch(ticker)
        -> ham OHLCV DataFrame
data/dataset.build_dataset(df)          (veya model/features.build_multi_dataset)
        -> split + train-only scaler + pencereler  = Dataset
model/train.train(dataset, cfg)
        -> TrainedModel  (ag + scaler + cfg)
model/evaluate.evaluate(dataset, model)
        -> naive dahil tum modeller yan yana, skill_score ile
model/registry.save(model)
        -> models/<TICKER>_<zaman>/{model.pt, meta.json}
model/predict.predict(model_path, recent_df)
        -> Forecast  {p10, p50, p90}  getiri + fiyat
```

---

## Değişmez kurallar (özet)

Ayrıntı ve gerekçeler `development-guide.md` §1'de. Kısaca:

- Scaler yalnızca train'e fit edilir; diskten okunur, yeniden fit edilmez.
- Hedef log getiridir; RMSE'yi güzel göstermek için fiyata çevirme.
- Naive baseline her metrik raporunda zorunlu; `skill_score > 0.01` değilse
  "yendi" denmez.
- Çıktı bir dağılımdır; quantile crossing yapısal olarak imkânsız.
- `predict()` sınırı log getiri uzayıdır; scaler modelin içinde yaşar.
- Kapsamanın hedefin **altında** olması, üstünde olmasından tehlikelidir.

---

## Sıradaki adım

`sentiment/` — FinBERT tabanlı, **ayrı bir risk katmanı** (fiyat modelinin
girdisine karıştırılmaz). Fiyat serisinin içinde olmayan bir sinyali getiren
tek kaynak budur; bugünkü "LSTM zaten hallediyordu diyemeyiz" sonucu onun
değerini artırır. Aynı dürüst protokol geçerli: VAL'de geliştir, temiz
holdout'ta karar ver, eşli t-testi yap, naive'i tabloda tut.
