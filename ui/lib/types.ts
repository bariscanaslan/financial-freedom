// API response types -- SOURCE OF TRUTH: ../../api/schemas.py.
// If the schema drifts, update here too; otherwise the UI silently shows the
// wrong field. NaN fields come back as null from the API -> `number | null`.

export interface Health {
  status: string;
  device: string;
  loaded_models: number;
}

export interface ModelSummary {
  ticker: string | null;
  saved_at: string | null;
  skill_score: number | null;
  coverage: number | null;
  nominal_cov: number | null;
}

export interface ModelsResponse {
  count: number;
  models: ModelSummary[];
}

export interface TrainingDeviceResponse {
  device: string;
}

export interface TrainingTicker {
  ticker: string;
  name: string;
  has_model: boolean;
  last_trained_at: string | null;
}

export interface TrainingCatalogResponse {
  as_of: string;
  count: number;
  tickers: TrainingTicker[];
}

export interface TrainingHistoryRow {
  epoch: number;
  train_loss: number;
  val_loss: number;
  max_epochs: number;
}

export interface TrainingJobResponse {
  id: string;
  ticker: string;
  status: "queued" | "preparing" | "training" | "evaluating" | "completed" | "failed";
  stage: string;
  device: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  config: Record<string, unknown>;
  progress: number | null;
  history: TrainingHistoryRow[];
  metrics: Record<string, string | number | boolean | null> | null;
  model_path: string | null;
  error: string | null;
  parameters: number | null;
  train_samples: number | null;
  val_samples: number | null;
  test_samples: number | null;
  best_epoch: number | null;
  best_val_loss: number | null;
}

export interface ModelMeta {
  ticker: string | null;
  saved_at: string | null;
  skill_score: number | null;
  coverage: number | null;
  nominal_cov: number | null;
  git_commit: string | null;
  note: string;
}

export type Quantiles = Record<string, number>; // {p10, p50, p90}

export interface PeriodForecast {
  label: string;
  trading_days: number;
  returns: Quantiles;
  prices: Quantiles;
  uncertainty: number;
  uncertainty_pct: number;
}

export interface ForecastResponse {
  ticker: string;
  as_of: string;
  anchor_price: number;
  quantiles: number[];
  returns: Quantiles;
  prices: Quantiles;
  uncertainty: number;
  uncertainty_pct: number;
  periods?: Record<string, PeriodForecast>;
  meta: ModelMeta;
}

export interface SavedPrediction {
  id: string;
  ticker: string;
  as_of: string;
  created_at: string;
  forecast: ForecastResponse;
}

export interface SavedPredictionsResponse {
  count: number;
  predictions: SavedPrediction[];
}

export interface PositionResponse {
  portfolio_id: string;
  as_of: string | null;
  holdings: Record<string, number>;
  cash: number;
}

export interface PositionRow {
  ticker: string;
  shares: number;
  price: number | null;
  value: number | null;
  weight: number | null;
  change_1d: number | null;
  change_1w: number | null;
  change_1m: number | null;
}

export interface PositionsResponse {
  portfolio_id: string;
  as_of: string | null;
  cash: number;
  total_value: number | null;
  positions: PositionRow[];
}

export interface ValuePoint {
  date: string;
  cash: number | null;
  position_value: number | null;
  total_value: number | null;
}

export interface ValueSeriesResponse {
  portfolio_id: string;
  points: ValuePoint[];
}

export interface MetricsResponse {
  portfolio_id: string;
  n_days: number;
  total_return: number;
  ann_return: number;
  ann_vol: number;
  sharpe: number | null;
  max_drawdown: number;
  beta: number | null;
  alpha: number | null;
}

// /report and /simulate rows (mirrors report.py / metrics.py to_row keys).
export interface ReportRow {
  portfolio: string;
  days: number;
  total_return: number | null;
  ann_return: number | null;
  ann_vol: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  beta: number | null;
  alpha: number | null;
}

export interface ReportResponse {
  portfolio_id: string;
  rows: ReportRow[];
}

export interface PortfolioForecastResponse {
  portfolio_id: string;
  as_of: string;
  current_value: number;
  cash: number;
  quantiles: number[];
  values: Quantiles;
  returns: Quantiles;
  warning: string;
  method?: string;
  correlation?: Record<string, Record<string, number>> | null;
  periods?: Record<string, {
    label: string; trading_days: number; values: Quantiles; returns: Quantiles;
    uncertainty: number; uncertainty_pct: number; method: string;
  }>;
}

export interface SavedRisk {
  id: string;
  portfolio_id: string;
  created_at: string;
  risk: PortfolioForecastResponse;
}

export interface SavedRisksResponse {
  count: number;
  risks: SavedRisk[];
}

export interface EventIn {
  type: string;
  timestamp: string;
  ticker?: string | null;
  quantity?: number;
  price?: number;
  cash?: number;
  fees?: number;
  note?: string;
}

export interface EventAppendResponse {
  portfolio_id: string;
  appended: EventIn;
  position: PositionResponse;
}

export type PortfolioKind = "actual" | "simulated";

export interface PortfolioSummary {
  id: string;
  name: string;
  kind: PortfolioKind;
  base_currency: string;
  created_at: string | null;
}

export interface PortfoliosResponse {
  count: number;
  portfolios: PortfolioSummary[];
}

export interface InvestEntry {
  ticker: string;
  cash: number;
}

export interface InvestRequest {
  entries: InvestEntry[];
  date?: string | null;
}

export interface Trade {
  side: "BUY" | "SELL";
  timestamp: string;
  ticker: string;
  quantity: number;
  price: number;
  fees: number;
  cash_value: number;
}

export interface TradesResponse {
  portfolio_id: string;
  trades: Trade[];
}

export interface PortfolioDraftAllocation {
  ticker: string; name: string | null; weight: number; amount: number;
  expected_return: number; uncertainty_pct: number; skill_score: number | null;
}

export interface PortfolioDraft {
  id: string; created_at: string; updated_at: string; name: string;
  investment_amount: number; risk_preference: "conservative" | "balanced" | "aggressive";
  horizon: "daily" | "weekly" | "monthly" | "quarterly" | "half_year" | "yearly" | "two_year"; max_positions: number;
  allocations: PortfolioDraftAllocation[]; feedback: string; disclaimer: string;
}

export interface PortfolioDraftJob {
  id: string; status: "queued" | "running" | "completed" | "failed";
  stage: string; progress: number; processed_models: number; total_models: number;
  created_at: string; finished_at: string | null; draft: PortfolioDraft | null; error: string | null;
  events: string[];
}

export interface PortfolioEvaluationSummary {
  id: string; portfolio_id: string; portfolio_name: string; created_at: string;
  as_of: string; horizon: string;
}
export interface PortfolioEvaluationPoint {
  date: string; actual_value: number; predicted_p10: number; predicted_p50: number;
  predicted_p90: number; error_pct: number; covered: boolean;
}
export interface PortfolioEvaluation extends PortfolioEvaluationSummary {
  risk_preference: string; investment_amount: number; positions: Record<string, unknown>[];
  points: PortfolioEvaluationPoint[]; metrics: Record<string, number | null>; note: string;
}
export interface PortfolioEvaluationsResponse {
  count: number; evaluations: PortfolioEvaluationSummary[];
}

export interface MarketRow {
  ticker: string;
  price: number | null;
  change_1d: number | null;
  change_1w: number | null;
  change_1m: number | null;
  has_model: boolean;
}

export interface MarketOverviewResponse {
  count: number;
  rows: MarketRow[];
}

export interface TrackedTicker {
  ticker: string;
  first_used: string | null;
  last_used: string | null;
  use_count: number;
}

export interface TickersResponse {
  count: number;
  tickers: TrackedTicker[];
}
