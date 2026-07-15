// Formatting and explicit log-return display conversion.
// null/NaN -> "—" (empty data is never shown as 0).

const EMPTY = "—";
let displayCurrency: "USD" | "TRY" = "USD";
let usdTryRate = 1;

export function configureMoney(currency: "USD" | "TRY", rate: number): void {
  displayCurrency = currency;
  usdTryRate = Number.isFinite(rate) && rate > 0 ? rate : 1;
}

function isEmpty(x: number | null | undefined): boolean {
  return x === null || x === undefined || Number.isNaN(x);
}

export function money(x: number | null | undefined, currency = "USD"): string {
  if (isEmpty(x)) return EMPTY;
  const convert = currency === "USD" && displayCurrency === "TRY";
  return new Intl.NumberFormat("tr-TR", {
    style: "currency",
    currency: convert ? "TRY" : currency,
    maximumFractionDigits: 2,
  }).format((x as number) * (convert ? usdTryRate : 1));
}

export function pct(x: number | null | undefined, digits = 2): string {
  if (isEmpty(x)) return EMPTY;
  return `${((x as number) * 100).toFixed(digits)}%`;
}

export function signedPct(x: number | null | undefined, digits = 2): string {
  if (isEmpty(x)) return EMPTY;
  const v = x as number;
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

export function simpleReturn(logReturn: number): number {
  return Math.expm1(logReturn);
}

export function num(x: number | null | undefined, digits = 2): string {
  if (isEmpty(x)) return EMPTY;
  return (x as number).toFixed(digits);
}

export function shares(x: number | null | undefined): string {
  if (isEmpty(x)) return EMPTY;
  return (x as number).toLocaleString("tr-TR", { maximumFractionDigits: 4 });
}

// Sign direction -> semantic color class (meaning only, not decorative).
export function signClass(x: number | null | undefined): string {
  if (isEmpty(x)) return "muted";
  if ((x as number) > 0) return "pos";
  if ((x as number) < 0) return "neg";
  return "muted";
}
