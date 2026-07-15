"""
API smoke test -- NETWORK-FREE.

Instead of a real model/network:
  - a TINY real model is placed in the registry (temp dir) -> real predict() path
  - the price provider returns synthetic dfs (no network)
  - the DB is a temp SQLite file with two portfolios (A, B) for isolation

Covers: health, models, predict schema + ordering + meta, injection/traversal
422s, registry CRUD, cash-per-ticker invest, positions period change, market
overview, tracked tickers, unknown-id 404, and portfolio delete.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Resolve device before anything else: tests run deterministically on CPU.
os.environ["SPP_DEVICE"] = "cpu"

import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.dataset import Scaler  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from model.config import ModelConfig  # noqa: E402
from model.nets import QuantileLSTM  # noqa: E402
from model.registry import save as save_model  # noqa: E402
from model.train import TrainedModel  # noqa: E402
from portfolio.events import Event, EventType  # noqa: E402

from api.deps import get_db, get_model_cache, get_price_provider  # noqa: E402
from api.main import app  # noqa: E402
from api.services.db import Database  # noqa: E402
from api.services.model_cache import ModelCache  # noqa: E402

SEQ = 5


def _make_model_dir() -> str:
    root = Path(tempfile.mkdtemp(prefix="spp_api_models_"))
    cfg = ModelConfig(seq_len=SEQ, horizon=1, input_dim=1, feature_names=("r",),
                      quantiles=(0.1, 0.5, 0.9), hidden_dim=4, num_layers=1, dropout=0.0)
    net = QuantileLSTM(quantiles=cfg.quantiles, input_dim=1, hidden_dim=4,
                       num_layers=1, horizon=1, dropout=0.0)
    scaler = Scaler(mean=0.0, std=0.02, fitted_on="TEST:train[2020..2023]")
    model = TrainedModel(net=net, scaler=scaler, cfg=cfg)
    save_model(model, ticker="TEST",
               metrics={"skill_score": 0.02, "coverage": 0.78, "nominal_cov": 0.80},
               path=root / "TEST_20240101_000000")
    save_model(model, ticker="TEST2",
               metrics={"skill_score": 0.01, "coverage": 0.79, "nominal_cov": 0.80},
               path=root / "TEST2_20240101_000000")
    return str(root)


class FakeProvider:
    """Synthetic price. NO network."""
    def __init__(self):
        idx = pd.bdate_range("2024-01-02", periods=30)
        self._df = pd.DataFrame(
            {"close": [100.0 + 0.1 * i for i in range(30)],
             "adj_close": [100.0 + 0.1 * i for i in range(30)]},
            index=idx,
        )

    def recent(self, ticker: str) -> pd.DataFrame:
        return self._df

    def refresh(self, ticker: str) -> pd.DataFrame:
        return self._df

    def refresh_intraday(self, ticker: str) -> pd.DataFrame:
        return self._df

    def latest_quote(self, ticker: str):
        return float(self._df["adj_close"].iloc[-1]), self._df.index[-1]

    def frames(self, tickers):
        return {t: self._df for t in tickers}

    def frames_live(self, tickers):
        return self.frames(tickers)


def _seed_db() -> tuple[Database, str, str]:
    db = Database(tempfile.mktemp(suffix=".db"))
    a = db.create_portfolio("A actual", "actual")["id"]
    b = db.create_portfolio("B sim", "simulated")["id"]
    # A: cash + TEST position
    db.append_event(Event(a, EventType.DEPOSIT, pd.Timestamp("2024-01-02"), cash=10_000.0))
    db.append_event(Event(a, EventType.BUY, pd.Timestamp("2024-01-03"),
                          ticker="TEST", quantity=10.0, price=100.0, fees=1.0))
    # B: cash only (isolation: must not see A's TEST)
    db.append_event(Event(b, EventType.DEPOSIT, pd.Timestamp("2024-01-02"), cash=5_000.0))
    return db, a, b


def _check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def main() -> int:
    print("smoke_api -- network-free HTTP verification")

    cache = ModelCache(_make_model_dir(), device="cpu")
    provider = FakeProvider()
    db, A, B = _seed_db()

    app.dependency_overrides[get_model_cache] = lambda: cache
    app.dependency_overrides[get_price_provider] = lambda: provider
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as client:
        # 1) health
        r = client.get("/health")
        _check("/health 200", r.status_code == 200 and r.json()["status"] == "ok",
               str(r.json()))

        # 2) models
        r = client.get("/models")
        body = r.json()
        tickers = [m["ticker"] for m in body["models"]]
        _check("/models lists TEST", r.status_code == 200 and "TEST" in tickers)
        skill = next(m["skill_score"] for m in body["models"] if m["ticker"] == "TEST")
        _check("/models has skill_score", skill is not None, str(skill))

        r = client.post("/market/cache/refresh", json={"ticker": "AAPL"})
        _check("manual market cache refresh", r.status_code == 200
               and r.json()["rows"] == 30 and r.json()["ticker"] == "AAPL", str(r.json()))

        # 3) predict
        r = client.post("/predict", json={"ticker": "TEST"})
        _check("/predict 200", r.status_code == 200, str(r.json()))
        d = r.json()
        rr, pp = d["returns"], d["prices"]
        _check("returns p10<=p50<=p90", rr["p10"] <= rr["p50"] <= rr["p90"], str(rr))
        _check("prices p10<=p50<=p90", pp["p10"] <= pp["p50"] <= pp["p90"], str(pp))
        _check("meta.skill_score set", d["meta"]["skill_score"] is not None)
        _check("uncertainty >= 0", d["uncertainty"] >= 0)
        _check("daily period present", "daily" in d["periods"], str(d["periods"]))

        r = client.post("/predictions", json={"ticker": "TEST"})
        _check("save prediction 200", r.status_code == 200, str(r.json()))
        saved_id = r.json()["id"]
        r = client.get("/predictions")
        saved = r.json()["predictions"]
        _check("saved prediction listed",
               r.status_code == 200 and any(p["id"] == saved_id for p in saved), str(saved))
        r = client.get(f"/predictions/{saved_id}")
        _check("prediction detail 200", r.status_code == 200 and r.json()["id"] == saved_id)
        r = client.delete(f"/predictions/{saved_id}")
        _check("prediction delete 200", r.status_code == 200 and r.json()["deleted"] is True)

        # 3b) predict recorded the ticker
        r = client.get("/tickers")
        tk = [t["ticker"] for t in r.json()["tickers"]]
        _check("/tickers records TEST", "TEST" in tk, str(tk))

        # 4) path traversal: model_path injection rejected
        r = client.post("/predict", json={"ticker": "TEST", "model_path": "/etc/passwd"})
        _check("model_path rejected (422)", r.status_code == 422, str(r.status_code))

        # 5) invalid ticker
        r = client.post("/predict", json={"ticker": "../etc"})
        _check("invalid ticker (422)", r.status_code == 422, str(r.status_code))

        # 6) negative quantity
        r = client.post(f"/portfolios/{A}/events",
                        json={"type": "BUY", "timestamp": "2024-01-05",
                              "ticker": "TEST", "quantity": -5, "price": 100})
        _check("negative quantity (422)", r.status_code == 422, str(r.status_code))

        # 7) portfolio_id injection in body rejected
        r = client.post(f"/portfolios/{A}/events",
                        json={"type": "DEPOSIT", "timestamp": "2024-01-05",
                              "cash": 1, "portfolio_id": B})
        _check("portfolio_id injection rejected (422)", r.status_code == 422,
               str(r.status_code))

        # 8) unknown portfolio id -> 404
        r = client.get("/portfolios/act_deadbeef00")
        _check("unknown id -> 404", r.status_code == 404, str(r.status_code))

        # 9) forecast + correlation warning (English)
        r = client.get(f"/portfolios/{A}/forecast")
        _check("/forecast 200", r.status_code == 200, str(r.json()))
        fj = r.json()
        _check("correlation warning set",
               bool(fj["warning"]) and "orrelation" in fj["warning"])
        vv = fj["values"]
        _check("forecast values p10<=p50<=p90", vv["p10"] <= vv["p50"] <= vv["p90"], str(vv))

        # 10) positions: per-stock shares/value + period change
        r = client.get(f"/portfolios/{A}/positions")
        _check("/positions 200", r.status_code == 200, str(r.json()))
        pjson = r.json()
        test_row = next((p for p in pjson["positions"] if p["ticker"] == "TEST"), None)
        _check("TEST position present", test_row is not None and test_row["shares"] == 10.0)
        _check("period change fields (1w/1m set)",
               test_row["change_1w"] is not None and test_row["change_1m"] is not None,
               str(test_row))

        # 10b) portfolio editing: BUY/SELL are persisted as trade events
        r = client.post(f"/portfolios/{A}/trades",
                        json={"side": "BUY", "ticker": "TEST", "amount": 500.0})
        _check("portfolio BUY trade", r.status_code == 200 and r.json()["side"] == "BUY",
               str(r.json()))
        r = client.post(f"/portfolios/{A}/trades",
                        json={"side": "SELL", "ticker": "TEST", "amount": 1.0})
        _check("portfolio SELL trade", r.status_code == 200 and r.json()["side"] == "SELL",
               str(r.json()))
        r = client.get(f"/portfolios/{A}/trades")
        sides = [trade["side"] for trade in r.json()["trades"]]
        _check("trade history persisted", "BUY" in sides and "SELL" in sides, str(sides))

        # 11) isolation: A holds TEST, B does not
        a = client.get(f"/portfolios/{A}").json()
        b = client.get(f"/portfolios/{B}").json()
        _check("A holds TEST", "TEST" in a["holdings"], str(a["holdings"]))
        _check("B isolated (no TEST)", "TEST" not in b["holdings"] and b["cash"] == 5000.0,
               str(b))

        # 12) registry: list contains both
        r = client.get("/portfolios")
        ids = {p["id"] for p in r.json()["portfolios"]}
        _check("registry lists A and B", {A, B} <= ids, str(ids))

        # 13) create + cash-per-ticker invest
        r = client.post("/portfolios", json={"name": "New", "kind": "actual"})
        _check("create portfolio 200", r.status_code == 200, str(r.json()))
        new_id = r.json()["id"]
        r = client.post(f"/portfolios/{new_id}/invest",
                        json={"entries": [{"ticker": "TEST", "cash": 2000.0}]})
        _check("invest 200", r.status_code == 200, str(r.json()))
        _check("invest created TEST position", "TEST" in r.json()["holdings"],
               str(r.json()))

        # 13b) model-supported draft -> edit/feedback -> simulated portfolio
        r = client.post("/portfolio-drafts", json={
            "name": "Model draft", "investment_amount": 3000,
            "risk_preference": "balanced", "horizon": "daily", "max_positions": 2,
        })
        _check("portfolio draft created", r.status_code == 200, str(r.json()))
        draft = r.json()
        draft_id = draft["id"]
        weights = {item["ticker"]: 1 for item in draft["allocations"]}
        r = client.patch(f"/portfolio-drafts/{draft_id}", json={
            "allocations": weights, "feedback": "Eşit ağırlık istiyorum.",
        })
        _check("draft edit and feedback persisted", r.status_code == 200
               and r.json()["feedback"] == "Eşit ağırlık istiyorum."
               and abs(sum(item["weight"] for item in r.json()["allocations"]) - 1) < 1e-9,
               str(r.json()))
        r = client.post(f"/portfolio-drafts/{draft_id}/apply", json={"kind": "simulated"})
        _check("draft applied to portfolio", r.status_code == 200 and r.json()["kind"] == "simulated",
               str(r.json()))
        draft_portfolio_id = r.json()["id"]
        holdings = client.get(f"/portfolios/{draft_portfolio_id}").json()["holdings"]
        _check("draft allocations invested", set(weights) <= set(holdings), str(holdings))

        # 14) market overview
        r = client.get("/market/overview")
        _check("/market/overview 200", r.status_code == 200, str(r.status_code))
        mrows = r.json()["rows"]
        aapl = next((x for x in mrows if x["ticker"] == "AAPL"), None)
        _check("overview has AAPL with price", aapl is not None and aapl["price"] is not None,
               str(aapl))

        # 15) delete portfolio -> subsequent read 404
        r = client.delete(f"/portfolios/{new_id}")
        _check("delete portfolio 200", r.status_code == 200, str(r.json()))
        r = client.get(f"/portfolios/{new_id}")
        _check("deleted portfolio -> 404", r.status_code == 404, str(r.status_code))

    app.dependency_overrides.clear()
    db.close()
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
