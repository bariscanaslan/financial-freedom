// Product frame shown on every page. No action recommendation.

export function Disclaimer() {
  return (
    <footer className="disclaimer" role="contentinfo">
      <strong>Bu ürün yatırım tavsiyesi vermez.</strong> Hiçbir çıktı alım veya
      satım önerisi değildir. Tahminler yalnızca dağılımı (p10/p50/p90) ve
      belirsizliği açıklar. Ayrıntılı gerekçe için <a href="/guide">Rehber</a>
      sayfasına bakın.
    </footer>
  );
}
