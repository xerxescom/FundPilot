from app.core.thresholds import get_thresholds


def test_threshold_config_loads_defaults():
    thresholds = get_thresholds()

    assert thresholds.pe_high_percentile == 0.85
    assert thresholds.portfolio_concentration == 0.3
    assert thresholds.correlation_high == 0.85
    assert thresholds.deep_drawdown == -0.25
