export interface GuideSection {
  id: string;
  title: string;
  paragraphs: string[];
}

export const GUIDE_INTRO =
  "Bu ürün, OLASILIKSAL günlük getiri tahmini ve portföy takibi aracıdır. " +
  "Amacı tahmin ve belirsizlik ölçümüdür; yatırım tavsiyesi vermez. Aşağıda " +
  "sistemin nasıl çalıştığı ve neyi vaat edip etmediği açıkça anlatılmaktadır.";

export const GUIDE: GuideSection[] = [
  {
    id: "target",
    title: "Neden fiyat değil logaritmik getiri",
    paragraphs: [
      "Model, fiyat SEVİYESİNİ değil logaritmik getiriyi (r = ln(P_t / P_{t-1})) tahmin eder. Fiyat seviyesi tahmininde model, 'dünün fiyatını kopyala' çözümüne kaçar; RMSE kusursuz görünür ancak bilgi değeri sıfırdır.",
      "Fiyat yalnızca SUNUM için dönüştürülür: P = referans * exp(r). Referans, hedef günden önceki günün kapanışıdır. Kalite her zaman getiri alanında değerlendirilir; fiyat RMSE değeri yanıltıcı biçimde iyi görünür.",
    ],
  },
  {
    id: "band",
    title: "p10 / p50 / p90 ve risk",
    paragraphs: [
      "Çıktı tek bir sayı değil, dağılımdır. p50 medyanı; p10 ve p90 ise %80'lik aralığın alt ve üst sınırlarını gösterir.",
      "Risk sinyali = p90 - p10. Geniş aralık, modelin belirsizliğinin yüksek olduğunu gösterir. Yalnızca nokta tahminine bakmak riski gizler; ürünün temel amacı aralığı göstermektir.",
    ],
  },
  {
    id: "skill",
    title: "skill_score ve saf referans model",
    paragraphs: [
      "Aşılması gereken referans, 'yarının getirisi = 0' diyen saf tahmindir (rastgele yürüyüş). skill_score = 1 - rmse_model / rmse_naive.",
      "skill_score 0,01'in ALTINDAYSA kazanç değil gürültü kabul edilir. Test aralığı birkaç gün kaydırıldığında işaret değişebilir. Bu nedenle arayüz küçük bir pozitif puanı başarı olarak sunmaz.",
      "Dürüst sonuç şudur: model, günlük tek değişkenli getirilerde saf tahmini anlamlı ölçüde geçmez. Tahmin sayfası güven aşılamak için değil, belirsizliği göstermek için kullanılır.",
    ],
  },
  {
    id: "coverage",
    title: "Kapsama / kalibrasyon",
    paragraphs: [
      "Kapsama, gerçek değerlerin p10-p90 aralığına düşme oranıdır; hedef yaklaşık %80'dir.",
      "Kapsamanın hedefin ALTINDA olması daha tehlikelidir: model riski olduğundan düşük gösterir ve gerçekte korunmadığınız hâlde korunduğunuzu düşünebilirsiniz.",
    ],
  },
  {
    id: "twr",
    title: "Portföy getirisi: TWR ve maliyetler",
    paragraphs: [
      "Toplam getiri zaman ağırlıklıdır (TWR): para yatırma ve çekme gibi dış nakit akışları getiriye DAHİL EDİLMEZ. Aksi hâlde kazanç ile para eklemek birbirine karışır. Temettü dış akış değildir ve getiriye dahildir.",
      "Simülasyon komisyon ve fiyat kaymasını İÇERİR. Aksi hâlde simülasyon sistematik olarak iyimser olur ve gerçek getiriyi abartır.",
      "Getiri tek başına anlamlı değildir; her portföy SPY karşılaştırma ölçütüne göre değerlendirilir.",
    ],
  },
  {
    id: "correlation",
    title: "Portföy riski: korelasyonun göz ardı edilmesi",
    paragraphs: [
      "Portföy düzeyindeki risk aralığı, pozisyonları bağımsız kabul etmez; tüm pozisyonlar aynı anda kendi kantillerine taşınır (komonotonik varsayım).",
      "Gerçek çeşitlendirme hesaba katılmadığından ihtiyatlı ve GENİŞ bir aralık oluşur. Bu nedenle risk aralığı her zaman bir uyarıyla gösterilir.",
    ],
  },
  {
    id: "portfolios",
    title: "Gerçek ve Simülasyon",
    paragraphs: [
      "Hisse sembollerini ve her biri için nakit tutarını seçerek portföy oluşturursunuz. Sistem, seçilen tarihte gerçek piyasa fiyatından alım yapar ve günlük, haftalık ve aylık değişimi takip eder.",
      "Gerçek portföy fiilî yatırımlarınızı, Simülasyon portföyü ise varsayımsal yatırımları gösterir. Birbirlerinden bağımsızdırlar ve portföy hesapları tahmin modeline bağlı değildir.",
    ],
  },
  {
    id: "advice",
    title: "Neden yatırım tavsiyesi değildir",
    paragraphs: [
      "Ürün hiçbir zaman 'al/sat' veya 'bu hisse yükselecek' demez. Çıktı yalnızca dağılımı ve belirsizliği açıklar.",
      "Ölçümlere göre model saf tahmini anlamlı ölçüde geçmez. Bu aracı karar mekanizması olarak değil, belirsizliği görünür kılan bir gösterge olarak kullanın.",
    ],
  },
];
