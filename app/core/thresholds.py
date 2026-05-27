from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ScoringThresholds(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pe_high_percentile: float = 0.85
    pe_supportive_ceiling: float = 0.80
    portfolio_concentration: float = 0.30
    correlation_high: float = 0.85
    deep_drawdown: float = -0.25
    high_volatility: float = 0.35
    near_term_return_1m_overheated: float = 0.08
    near_term_return_3m_overheated: float = 0.15
    peer_rank_low: float = 0.30
    peer_rank_high: float = 0.70
    portfolio_drawdown_alert: float = -0.08
    daily_drop_alert: float = -0.03
    score_drop_alert: float = 10.0


def _threshold_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "scoring_thresholds.json"


@lru_cache
def get_thresholds() -> ScoringThresholds:
    path = _threshold_path()
    if not path.exists():
        return ScoringThresholds()
    return ScoringThresholds.model_validate(json.loads(path.read_text(encoding="utf-8")))
