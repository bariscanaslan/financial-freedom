import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// --- API fully mocked: the smoke test runs network-free ---
const h = vi.hoisted(() => {
  class ApiError extends Error {
    status: number;
    code: string;
    constructor(m: string, s: number, c: string) {
      super(m);
      this.status = s;
      this.code = c;
    }
    get isModelMissing() {
      return this.status === 404 && this.code === "not_found";
    }
  }
  return {
    ApiError,
    getHealth: vi.fn(),
    getModels: vi.fn(),
    getTrainingCatalog: vi.fn(),
    predict: vi.fn(),
    getMarketOverview: vi.fn(),
    getTickers: vi.fn(),
    listPortfolios: vi.fn(),
    createPortfolio: vi.fn(),
    deletePortfolio: vi.fn(),
    invest: vi.fn(),
    getPosition: vi.fn(),
    getPositions: vi.fn(),
    getValue: vi.fn(),
    getMetrics: vi.fn(),
    getReport: vi.fn(),
    getForecast: vi.fn(),
    getTrades: vi.fn(),
    appendEvent: vi.fn(),
    getPortfolioAlert: vi.fn(),
    savePortfolioAlert: vi.fn(),
    testPortfolioAlert: vi.fn(),
  };
});

vi.mock("@/lib/api", () => h);

import Dashboard from "@/app/page";
import PortfolioPage from "@/app/portfolio/page";
import PredictPage from "@/app/predict/page";
import RiskPage from "@/app/risk/page";
import GuidePage from "@/app/guide/page";
import { CorrelationWarning } from "@/components/CorrelationWarning";
import { RiskBadge } from "@/components/RiskBadge";
import { PositionsTable } from "@/components/PositionsTable";
import { MarketTable } from "@/components/MarketTable";
import type {
  ForecastResponse,
  MarketOverviewResponse,
  MetricsResponse,
  ModelsResponse,
  PortfolioForecastResponse,
  PortfoliosResponse,
  PositionsResponse,
  ReportResponse,
} from "@/lib/types";

const forecast: ForecastResponse = {
  ticker: "AAPL",
  as_of: "2024-02-12",
  anchor_price: 190,
  quantiles: [0.1, 0.5, 0.9],
  returns: { p10: -0.01, p50: 0.002, p90: 0.015 },
  prices: { p10: 188, p50: 190.4, p90: 193 },
  uncertainty: 5,
  uncertainty_pct: 0.026,
  meta: {
    ticker: "AAPL",
    saved_at: "2026-01-01",
    skill_score: -0.003,
    coverage: 0.78,
    nominal_cov: 0.8,
    git_commit: "abc",
    note: "Descriptive metric.",
  },
};

const positions: PositionsResponse = {
  portfolio_id: "act_1",
  as_of: "2024-02-12",
  cash: 1000,
  total_value: 11000,
  positions: [
    { ticker: "AAPL", shares: 10, price: 190, value: 1900, weight: 0.19,
      change_1d: 0.001, change_1w: 0.01, change_1m: -0.02 },
  ],
};

const metrics: MetricsResponse = {
  portfolio_id: "act_1", n_days: 100, total_return: 0.05, ann_return: 0.12,
  ann_vol: 0.2, sharpe: 0.6, max_drawdown: -0.1, beta: 1.0, alpha: 0.01,
};

const report: ReportResponse = {
  portfolio_id: "act_1",
  rows: [
    { portfolio: "actual", days: 100, total_return: 0.05, ann_return: 0.12,
      ann_vol: 0.2, sharpe: 0.6, max_drawdown: -0.1, beta: 1, alpha: 0.01 },
    { portfolio: "benchmark (SPY)", days: 100, total_return: 0.08, ann_return: 0.2,
      ann_vol: 0.15, sharpe: 1.1, max_drawdown: -0.05, beta: null, alpha: null },
  ],
};

const pforecast: PortfolioForecastResponse = {
  portfolio_id: "act_1", as_of: "2024-02-12", current_value: 11000, cash: 1000,
  quantiles: [0.1, 0.5, 0.9],
  values: { p10: 10800, p50: 11010, p90: 11250 },
  returns: { p10: -0.018, p50: 0.0009, p90: 0.022 },
  warning:
    "Correlation ignored (comonotonic assumption): positions were not treated as independent. NOT an action recommendation.",
};

const models: ModelsResponse = {
  count: 1,
  models: [{ ticker: "AAPL", saved_at: "2026-01-01", skill_score: -0.003, coverage: 0.78, nominal_cov: 0.8 }],
};

const portfolios: PortfoliosResponse = {
  count: 2,
  portfolios: [
    { id: "act_1", name: "My Actual", kind: "actual", base_currency: "USD", created_at: "2026-01-01" },
    { id: "sim_1", name: "My Sim", kind: "simulated", base_currency: "USD", created_at: "2026-01-01" },
  ],
};

const market: MarketOverviewResponse = {
  count: 1,
  rows: [{ ticker: "AAPL", price: 190, change_1d: 0.001, change_1w: 0.01, change_1m: -0.02, has_model: true }],
};

beforeEach(() => {
  vi.clearAllMocks();
  h.listPortfolios.mockResolvedValue(portfolios);
  h.getPositions.mockResolvedValue(positions);
  h.getMetrics.mockResolvedValue(metrics);
  h.getReport.mockResolvedValue(report);
  h.getForecast.mockResolvedValue(pforecast);
  h.getTrades.mockResolvedValue({ portfolio_id: "act_1", trades: [] });
  h.getPortfolioAlert.mockResolvedValue(null);
  h.savePortfolioAlert.mockResolvedValue({});
  h.testPortfolioAlert.mockResolvedValue({ status: "sent", channels: [], errors: [] });
  h.getModels.mockResolvedValue(models);
  h.getTrainingCatalog.mockResolvedValue({ as_of: "2026-01-01", count: 1, tickers: [{ ticker: "AAPL", name: "Apple", has_model: true, last_trained_at: "2026-01-01T12:00:00" }] });
  h.getMarketOverview.mockResolvedValue(market);
  h.predict.mockResolvedValue(forecast);
});

describe("honesty components", () => {
  it("correlation warning is in the DOM and shows its text", () => {
    render(<CorrelationWarning text="korelasyon hesaba katılmadı" />);
    expect(screen.getByTestId("correlation-warning")).toHaveTextContent(
      "korelasyon hesaba katılmadı",
    );
  });

  it("low skill_score shows a warning and NO 'reliable' badge", () => {
    render(<RiskBadge meta={forecast.meta} />);
    expect(screen.getByTestId("skill-warning")).toBeInTheDocument();
    expect(screen.queryByTestId("reliable-badge")).toBeNull();
  });

  it("empty holdings -> 'no open positions' (not 0)", () => {
    render(<PositionsTable data={{ ...positions, positions: [] }} />);
    expect(screen.getByTestId("empty-state")).toHaveTextContent(/açık pozisyon yok/i);
  });
});

describe("predict page", () => {
  it("no model -> clear message, no band", async () => {
    h.predict.mockRejectedValueOnce(new h.ApiError("missing", 404, "not_found"));
    render(<PredictPage />);
    fireEvent.change(screen.getByLabelText("Hisse sembolü"), { target: { value: "ZZZZ" } });
    fireEvent.click(screen.getByRole("button", { name: "Tahmin et" }));
    expect(await screen.findByTestId("model-missing")).toBeInTheDocument();
    expect(screen.queryByTestId("forecast-band")).toBeNull();
  });

  it("with a model -> period overview + low-skill warning; no reliable badge", async () => {
    render(<PredictPage />);
    fireEvent.change(screen.getByLabelText("Hisse sembolü"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByRole("button", { name: "Tahmin et" }));
    expect(await screen.findByText("Günlük")).toBeInTheDocument();
    expect(screen.getByTestId("skill-warning")).toBeInTheDocument();
    expect(screen.queryByTestId("reliable-badge")).toBeNull();
  });
});

describe("risk page", () => {
  it("correlation warning renders BEFORE the band", async () => {
    render(<RiskPage />);
    const warn = await screen.findByTestId("correlation-warning");
    const band = await screen.findByTestId("forecast-band");
    expect(warn.compareDocumentPosition(band) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe("page render smoke + market overview", () => {
  it("guide renders", () => {
    render(<GuidePage />);
    expect(screen.getByText("Rehber")).toBeInTheDocument();
  });

  it("dashboard renders two value cards and the market table", async () => {
    render(<Dashboard />);
    expect(await screen.findAllByTestId("value-card")).toHaveLength(2);
    expect(await screen.findByTestId("market-table")).toBeInTheDocument();
  });

  it("portfolio page renders a positions table and a builder", async () => {
    render(<PortfolioPage />);
    expect(await screen.findByTestId("positions-table")).toBeInTheDocument();
    expect(screen.getByLabelText("Portföy adı")).toBeInTheDocument();
  });

  it("market table shows a +/- signed change with the value (not color alone)", () => {
    render(<MarketTable rows={market.rows} />);
    const table = screen.getByTestId("market-table");
    expect(table).toHaveTextContent("+0.10%");
  });
});
