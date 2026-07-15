// State views: loading / error / empty / model-missing handled separately.
// Empty data is never shown as 0; "no data" and "value is 0" are different.

import { ApiError } from "@/lib/api";

export function Loading({ label = "Yükleniyor" }: { label?: string }) {
  return (
    <p className="state muted" role="status" aria-live="polite">
      {label}…
    </p>
  );
}

export function Empty({ message }: { message: string }) {
  return (
    <p className="state muted" data-testid="empty-state">
      {message}
    </p>
  );
}

export function ModelMissing({ ticker }: { ticker: string }) {
  return (
    <div className="state note muted" data-testid="model-missing">
      <strong>{ticker}</strong> için eğitilmiş model yok. Bu sembol için tahmin
      üretilmez ve yapay bir aralık gösterilmez. Yalnızca eğitilmiş modeli olan
      hisseler için tahmin sunulur.
    </div>
  );
}

export function ErrorView({ error }: { error: unknown }) {
  // Internal detail (stack/file path) never leaks; the API's short message shows.
  const msg = error instanceof ApiError
    ? "İstek tamamlanamadı. Lütfen daha sonra tekrar deneyin."
    : "Beklenmeyen bir hata oluştu.";
  return (
    <div className="state error" role="alert" data-testid="error-state">
      Hata: {msg}
    </div>
  );
}
