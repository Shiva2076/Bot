import asyncio

import pytest
from fastapi import HTTPException

from config import settings
from services.auth.api_key_auth import require_api_key


def test_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_api_key(""))
    assert exc.value.status_code == 401


def test_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_api_key("nope"))
    assert exc.value.status_code == 401


def test_accepts_matching_key(monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "secret")
    assert asyncio.run(require_api_key("secret")) == "secret"


def test_unconfigured_key_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "app_api_key", "")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_api_key("anything"))
    assert exc.value.status_code == 503
