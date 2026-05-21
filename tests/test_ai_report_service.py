from app.services.ai.report_service import _sanitize


def test_sanitize_removes_forbidden_terms():
    content = "这只基金可以立即买入，并且保证收益。"

    cleaned = _sanitize(content)

    assert "立即买入" not in cleaned
    assert "保证收益" not in cleaned
