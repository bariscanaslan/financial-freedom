// Non-silenceable correlation warning (A4). Text comes from the API
// (forecast_link warning) -- the UI does not invent it. Must render BEFORE the band.

export function CorrelationWarning({ text }: { text: string }) {
  return (
    <div role="alert" className="warn-box" data-testid="correlation-warning">
      <strong>Korelasyon bilgisi.</strong> {text}
    </div>
  );
}
