"""
Model katmani: olasiliksal (quantile) fiyat tahmini.

Cikti bir SAYI degil bir DAGILIMDIR: p10 / p50 / p90.
    p50            -> nokta tahmini
    p90 - p10      -> BELIRSIZLIK = risk sinyali

Butun modeller (naive dahil) ayni arayuzu paylasir:
    fit(dataset) -> self
    predict(X_scaled) -> (N, horizon, Q)  LOG GETIRI uzayinda
"""

from .baselines import (
    ConstantGaussianModel,
    EWMAVolModel,
    NaiveModel,
    QuantileForecaster,
    default_baselines,
)
from .config import MODEL_DIR, ModelConfig, get_device
from .conformal import ConformalWrapper
from .device import (
    DeviceInfo,
    available_devices,
    ask_device,
    best_device,
    describe,
    free_cache,
    reset_device,
    select_device,
    set_device,
)
from .evaluate import evaluate, report
from .features import MultiDataset, build_features, build_multi_dataset
from .hybrid import HybridEWMALSTM
from .losses import pinball_loss
from .metrics import evaluate_predictions, skill_score
from .nets import QuantileLSTM
from .predict import Forecast, predict
from .registry import list_models, load, save
from .train import TrainedModel, seed_everything, train

__all__ = [
    "ModelConfig", "get_device", "MODEL_DIR",
    # cihaz katmani -- cuda / xpu / mps / cpu, makineden bagimsiz
    "select_device", "set_device", "reset_device", "ask_device",
    "available_devices", "best_device", "free_cache", "describe", "DeviceInfo",
    "QuantileLSTM", "pinball_loss",
    "QuantileForecaster", "NaiveModel", "ConstantGaussianModel", "EWMAVolModel",
    "default_baselines",
    "build_features", "build_multi_dataset", "MultiDataset",
    "HybridEWMALSTM", "ConformalWrapper",
    "evaluate_predictions", "skill_score",
    "train", "TrainedModel", "seed_everything",
    "save", "load", "list_models",
    "evaluate", "report",
    "predict", "Forecast",
]
