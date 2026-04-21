"""Unit tests for pyscorpiontrack."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pyscorpiontrack import (
    ScorpionTrackClient,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShareUnavailableError,
)


class _FakeResponse:
    def __init__(self, status: int, payload) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requested_urls: list[str] = []

    def get(self, url: str):
        self.requested_urls.append(url)
        return self._response


def test_extract_token_accepts_raw_token() -> None:
    assert ScorpionTrackClient.extract_token(" abc123 ") == "abc123"


def test_extract_token_accepts_share_url() -> None:
    assert (
        ScorpionTrackClient.extract_token(
            "https://app.scorpiontrack.com/shared/location?token=abc123"
        )
        == "abc123"
    )


def test_extract_token_rejects_missing_query_parameter() -> None:
    with pytest.raises(ScorpionTrackInvalidTokenError):
        ScorpionTrackClient.extract_token("https://app.scorpiontrack.com/shared/location")


@pytest.mark.asyncio
async def test_async_get_share_parses_payload() -> None:
    payload = {
        "data": {
            "id": 101,
            "token": "abc123",
            "title": "Family Cars",
            "created_at": "2026-04-20T10:00:00Z",
            "expires_at": "2026-04-21T10:00:00",
            "user": {
                "first_name": "Ash",
                "last_name": "By",
                "distance_units": "miles",
            },
            "vehicles": [
                {
                    "id": 2001,
                    "registration": "AB12 CDE",
                    "make": "Audi",
                    "model": "A4",
                    "latest_position": {
                        "lat": "51.5007",
                        "lng": "-0.1246",
                        "timestamp": "2026-04-20T10:05:00Z",
                        "speed": "48.4",
                        "ignition": "1",
                        "bearing": "180",
                        "address": "London",
                    },
                }
            ],
        }
    }
    session = _FakeSession(_FakeResponse(200, payload))
    client = ScorpionTrackClient(session=session, token="abc123")

    share = await client.async_get_share()

    assert share.id == 101
    assert share.title == "Family Cars"
    assert share.owner_name == "Ash By"
    assert share.uses_miles is True
    assert share.expires_at == datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc)
    assert len(share.vehicles) == 1
    assert share.vehicles[0].display_name == "AB12 CDE"
    assert share.vehicles[0].status == "moving"
    assert session.requested_urls == [
        "https://api2.fleet.scorpiontrack.com/v1/location-shares/abc123/view"
    ]


@pytest.mark.asyncio
async def test_async_get_share_raises_for_empty_payload() -> None:
    session = _FakeSession(_FakeResponse(200, {"data": None}))
    client = ScorpionTrackClient(session=session, token="abc123")

    with pytest.raises(ScorpionTrackShareUnavailableError):
        await client.async_get_share()
