from agents import institutional_agent
from services.institutional_data import _parse_fii_dii


def test_empty_response_is_unavailable_not_random():
    result = _parse_fii_dii([])
    assert result["available"] is False
    assert "fii_net" not in result


def test_missing_dii_rows_is_unavailable():
    result = _parse_fii_dii([{"category": "FII/FPI", "netVal": "100"}])
    assert result["available"] is False


def test_live_rows_parse_without_fake_constants():
    result = _parse_fii_dii([
        {"category": "FII/FPI", "netVal": "-1200.5"},
        {"category": "DII", "netVal": "900.25"},
    ])
    assert result == {"available": True, "fii_net": -1200.5, "dii_net": 900.25, "source": "NSE Live"}


def test_agent_excludes_unavailable_data():
    output = institutional_agent.analyze({"available": False, "source": "unavailable", "reason": "HTTP 403"}, "^NSEI")
    assert output["available"] is False
    assert output["score"] == 0
