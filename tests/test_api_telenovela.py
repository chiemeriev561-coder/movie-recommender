import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import api

client = TestClient(api.app)


def test_telenovela_detection():
    # Soap opera genre ID 10766
    soap_data = {"id": 100, "genres": [{"id": 10766, "name": "Soap"}], "original_language": "es"}
    # Drama spanish
    drama_es = {"id": 101, "genres": [{"id": 18, "name": "Drama"}], "original_language": "es"}
    # Action english
    action_en = {"id": 102, "genres": [{"id": 28, "name": "Action"}], "original_language": "en"}

    import asyncio
    assert asyncio.run(api.is_telenovela_series(100, soap_data)) is True
    assert asyncio.run(api.is_telenovela_series(101, drama_es)) is True
    assert asyncio.run(api.is_telenovela_series(102, action_en)) is False


def test_get_telenovela_episode_stream(monkeypatch):
    telenovela_info = {
        "id": 1234,
        "name": "La Reina del Sur",
        "genres": [{"id": 10766, "name": "Soap"}],
        "original_language": "es"
    }

    monkeypatch.setattr(api, "get_tv_series_basic_info", AsyncMock(return_value=telenovela_info))

    # Mock httpx HEAD request success
    mock_resp = AsyncMock()
    mock_resp.status_code = 200

    mock_client = AsyncMock()
    mock_client.head.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = client.get("/api/tv/telenovela/1234/season/1/episode/1/stream")
        assert response.status_code == 200
        data = response.json()
        assert data["stream_url"] == "https://nontongo.win/tv/1234/1/1"
        assert data["provider"] == "Nontongo.win"
        assert data["is_telenovela"] is True
