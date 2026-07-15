// Typed API client -- the ONE fetch point. No raw fetch in components.
// Internal details (file paths / model_path) are never sent; the user only
// supplies a ticker and portfolio_id (api/ A1).

import { API_URL } from "./config";
import type {
  EventAppendResponse,
  EventIn,
  ForecastResponse,
  Health,
  InvestRequest,
  MarketOverviewResponse,
  MetricsResponse,
  ModelsResponse,
  PortfolioForecastResponse,
  PortfolioDraft,
  PortfolioDraftJob,
  PortfolioEvaluation,
  PortfolioEvaluationsResponse,
  PortfolioKind,
  PortfoliosResponse,
  PortfolioSummary,
  PositionResponse,
  PositionsResponse,
  ReportResponse,
  SavedPrediction,
  SavedPredictionsResponse,
  SavedRisk,
  SavedRisksResponse,
  TickersResponse,
  TrainingDeviceResponse,
  TrainingCatalogResponse,
  TrainingJobResponse,
  Trade,
  TradesResponse,
  ValueSeriesResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(message: string, status: number, code: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
  get isModelMissing(): boolean {
    return this.status === 404 && this.code === "not_found";
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    // Network/server unreachable -- without leaking internal detail.
    throw new ApiError("could not reach the server", 0, "network");
  }
  if (!res.ok) {
    let detail = res.statusText || "request failed";
    let code = "error";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      if (typeof body?.code === "string") code = body.code;
    } catch {
      // body is not JSON -- fall back to statusText
    }
    throw new ApiError(detail, res.status, code);
  }
  return (await res.json()) as T;
}

export const getHealth = () => req<Health>("/health");
export const getModels = () => req<ModelsResponse>("/models");
export const getTrainingDevice = () =>
  req<TrainingDeviceResponse>("/training/device");
export const getTrainingCatalog = () =>
  req<TrainingCatalogResponse>("/training/catalog");
export const startTraining = (ticker: string, horizon = 21) =>
  req<TrainingJobResponse>("/training", {
    method: "POST",
    body: JSON.stringify({ ticker, horizon }),
  });
export const getTrainingStatus = (id: string) =>
  req<TrainingJobResponse>(`/training/${encodeURIComponent(id)}`);

export const predict = (ticker: string) =>
  req<ForecastResponse>("/predict", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
export const savePrediction = (ticker: string) =>
  req<SavedPrediction>("/predictions", {
    method: "POST",
    body: JSON.stringify({ ticker }),
  });
export const listPredictions = () =>
  req<SavedPredictionsResponse>("/predictions");
export const getPrediction = (id: string) =>
  req<SavedPrediction>(`/predictions/${encodeURIComponent(id)}`);
export const deletePrediction = (id: string) =>
  req<{ id: string; deleted: boolean }>(`/predictions/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

export const getMarketOverview = () =>
  req<MarketOverviewResponse>("/market/overview");
export const getUsdTryRate = () =>
  req<{ base: "USD"; quote: "TRY"; rate: number; as_of: string; source: string }>("/market/fx/usd-try");
export const refreshMarketCache = (ticker: string) =>
  req<{ ticker: string; rows: number; first_date: string; last_date: string }>("/market/cache/refresh", {
    method: "POST", body: JSON.stringify({ ticker }),
  });
export const refreshAllMarketCaches = () =>
  req<{ total: number; refreshed: number; failed: string[] }>("/market/cache/refresh-all", { method: "POST" });

export const getTickers = () => req<TickersResponse>("/tickers");

const pid = (id: string) => encodeURIComponent(id);

// -- portfolio registry --
export const listPortfolios = () => req<PortfoliosResponse>("/portfolios");
export const createPortfolio = (name: string, kind: PortfolioKind) =>
  req<PortfolioSummary>("/portfolios", {
    method: "POST",
    body: JSON.stringify({ name, kind }),
  });
export const deletePortfolio = (id: string) =>
  req<{ portfolio_id: string; deleted: boolean }>(`/portfolios/${pid(id)}`, {
    method: "DELETE",
  });
export const invest = (id: string, body: InvestRequest) =>
  req<PositionResponse>(`/portfolios/${pid(id)}/invest`, {
    method: "POST",
    body: JSON.stringify(body),
  });
export const createTrade = (id: string, body: {
  side: "BUY" | "SELL"; ticker: string; amount: number; date?: string;
}) => req<Trade>(`/portfolios/${pid(id)}/trades`, {
  method: "POST", body: JSON.stringify(body),
});
export const getTrades = (id: string) =>
  req<TradesResponse>(`/portfolios/${pid(id)}/trades`);

export const createPortfolioDraft = (body: {
  name: string; investment_amount: number; risk_preference: string;
  horizon: string; max_positions: number;
}) => req<PortfolioDraft>("/portfolio-drafts", { method: "POST", body: JSON.stringify(body) });
export const startPortfolioDraft = (body: {
  name: string; investment_amount: number; risk_preference: string;
  horizon: string; max_positions: number;
}) => req<PortfolioDraftJob>("/portfolio-drafts/generate", { method: "POST", body: JSON.stringify(body) });
export const getPortfolioDraftStatus = (id: string) =>
  req<PortfolioDraftJob>(`/portfolio-drafts/generate/${encodeURIComponent(id)}`);
export const updatePortfolioDraft = (id: string, body: { allocations: Record<string, number>; feedback: string }) =>
  req<PortfolioDraft>(`/portfolio-drafts/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) });
export const applyPortfolioDraft = (id: string, kind: PortfolioKind) =>
  req<PortfolioSummary>(`/portfolio-drafts/${encodeURIComponent(id)}/apply`, { method: "POST", body: JSON.stringify({ kind }) });
export const listPortfolioEvaluations = () =>
  req<PortfolioEvaluationsResponse>("/portfolio-evaluations");
export const getPortfolioEvaluation = (id: string) =>
  req<PortfolioEvaluation>(`/portfolio-evaluations/${encodeURIComponent(id)}`);

// -- portfolio reads --
export const getPosition = (id: string) =>
  req<PositionResponse>(`/portfolios/${pid(id)}`);
export const getPositions = (id: string) =>
  req<PositionsResponse>(`/portfolios/${pid(id)}/positions`);
export const getValue = (id: string) =>
  req<ValueSeriesResponse>(`/portfolios/${pid(id)}/value`);
export const getMetrics = (id: string) =>
  req<MetricsResponse>(`/portfolios/${pid(id)}/metrics`);
export const getReport = (id: string) =>
  req<ReportResponse>(`/portfolios/${pid(id)}/report`);
export const getForecast = (id: string) =>
  req<PortfolioForecastResponse>(`/portfolios/${pid(id)}/forecast`);
export const saveRisk = (portfolioId: string) =>
  req<SavedRisk>("/risks", {
    method: "POST",
    body: JSON.stringify({ portfolio_id: portfolioId }),
  });
export const listRisks = () => req<SavedRisksResponse>("/risks");
export const getRisk = (id: string) =>
  req<SavedRisk>(`/risks/${encodeURIComponent(id)}`);
export const deleteRisk = (id: string) =>
  req<{ id: string; deleted: boolean }>(`/risks/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });

// Append-only. Corrections are reversing events.
export const appendEvent = (id: string, event: EventIn) =>
  req<EventAppendResponse>(`/portfolios/${pid(id)}/events`, {
    method: "POST",
    body: JSON.stringify(event),
  });
