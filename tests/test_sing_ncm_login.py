from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytest.importorskip("pallas.api.runtime")

import nonebot  # noqa: E402

nonebot.init(driver="nonebot.drivers.none:Driver")  # noqa: E402

from pallas_plugin_sing import ncm_login  # noqa: E402


class JsonResponse:
    def __init__(self, payload: object):
        self.payload = payload

    def json(self) -> object:
        return self.payload


@pytest.mark.asyncio
async def test_get_song_title_with_artist_returns_name_and_artists(monkeypatch: pytest.MonkeyPatch) -> None:
    get = AsyncMock(return_value=JsonResponse({"name": "青花瓷", "artists": ["周杰伦"]}))
    monkeypatch.setattr(ncm_login.HTTPXClient, "get", get)
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: {"Authorization": "Bearer secret-token"})
    monkeypatch.setattr(ncm_login, "sing_server_url", lambda: "http://media:9099")

    result = await ncm_login.get_song_title_with_artist(123)

    assert result == ("青花瓷", ["周杰伦"])
    get.assert_awaited_once_with(
        "http://media:9099/v1/ncm/songs/123",
        headers={"Authorization": "Bearer secret-token"},
        timeout=ncm_login.NCM_SEARCH_TIMEOUT,
    )


@pytest.mark.asyncio
async def test_get_song_title_with_artist_falls_back_without_artists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ncm_login.HTTPXClient,
        "get",
        AsyncMock(return_value=JsonResponse({"name": "青花瓷", "artists": []})),
    )
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: {"Authorization": "Bearer secret-token"})

    assert await ncm_login.get_song_title_with_artist(123) == ("青花瓷", [])


@pytest.mark.asyncio
async def test_get_song_title_with_artist_returns_none_on_empty_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ncm_login.HTTPXClient,
        "get",
        AsyncMock(return_value=JsonResponse({"name": "", "artists": []})),
    )
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: {"Authorization": "Bearer secret-token"})

    assert await ncm_login.get_song_title_with_artist(123) is None


@pytest.mark.asyncio
async def test_get_song_title_with_artist_returns_none_on_missing_service(monkeypatch: pytest.MonkeyPatch) -> None:
    get = AsyncMock(return_value=None)
    monkeypatch.setattr(ncm_login.HTTPXClient, "get", get)
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: {"Authorization": "Bearer secret-token"})

    assert await ncm_login.get_song_title_with_artist(123) is None
    get.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_song_title_with_artist_does_not_request_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get = AsyncMock()
    monkeypatch.setattr(ncm_login.HTTPXClient, "get", get)
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: None)

    assert await ncm_login.get_song_title_with_artist(123) is None
    get.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_song_id_keeps_numeric_shortcut(monkeypatch: pytest.MonkeyPatch) -> None:
    get = AsyncMock()
    monkeypatch.setattr(ncm_login.HTTPXClient, "get", get)

    assert await ncm_login.get_song_id("123") == "123"
    get.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_song_id_uses_authenticated_media_search(monkeypatch: pytest.MonkeyPatch) -> None:
    get = AsyncMock(return_value=JsonResponse({"song_id": 123}))
    monkeypatch.setattr(ncm_login.HTTPXClient, "get", get)
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: {"Authorization": "Bearer secret-token"})
    monkeypatch.setattr(ncm_login, "sing_server_url", lambda: "http://media:9099")

    assert await ncm_login.get_song_id("青花瓷") == 123
    get.assert_awaited_once_with(
        "http://media:9099/v1/ncm/search",
        params={"q": "青花瓷"},
        headers={"Authorization": "Bearer secret-token"},
        timeout=ncm_login.NCM_SEARCH_TIMEOUT,
    )


@pytest.mark.asyncio
async def test_get_song_id_returns_none_for_missing_token_or_invalid_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get = AsyncMock()
    monkeypatch.setattr(ncm_login.HTTPXClient, "get", get)
    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: None)
    assert await ncm_login.get_song_id("青花瓷") is None
    get.assert_not_awaited()

    monkeypatch.setattr(ncm_login, "ncm_api_headers", lambda: {"Authorization": "Bearer secret-token"})
    get.return_value = JsonResponse({"song_id": "not numeric"})
    assert await ncm_login.get_song_id("青花瓷") is None
