"""Unit tests for pyscorpiontrack."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from types import TracebackType
from typing import cast
from urllib.parse import quote

from aiohttp import ClientError, ClientSession
import pytest

from pyscorpiontrack import (
    ScorpionTrackClient,
    ScorpionTrackConnectionError,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShareUnavailableError,
)

SECRET_TOKEN = "TOPS/private-share/NEND"
SECRET_MARKERS = (SECRET_TOKEN, quote(SECRET_TOKEN, safe=""), "TOPS", "NEND")


class _FakeResponse:
    def __init__(
        self,
        status: int,
        payload: object,
        *,
        json_error: Exception | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        self._json_error = json_error

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def json(self, content_type: str | None = None) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requested_urls: list[str] = []

    def get(self, url: str) -> _FakeResponse:
        self.requested_urls.append(url)
        return self._response


class _FailingSession:
    def get(self, url: str) -> None:
        raise ClientError(f"Request failed for {url}")


class _TimeoutResponse(_FakeResponse):
    async def __aenter__(self) -> _FakeResponse:
        raise TimeoutError(f"Timed out fetching {SECRET_TOKEN}")


def _client(
    session: _FakeSession | _FailingSession,
    token: str = "abc123",
) -> ScorpionTrackClient:
    # ClientSession is concrete; these doubles intentionally implement only get().
    return ScorpionTrackClient(session=cast(ClientSession, session), token=token)


def _assert_secret_absent(text: str) -> None:
    for marker in SECRET_MARKERS:
        assert marker not in text


def _exception_chain_text(error: BaseException) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.extend((str(current), repr(current)))
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def _log_text(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def _assert_safe_logs(caplog: pytest.LogCaptureFixture) -> None:
    _assert_secret_absent(_log_text(caplog))
    assert not [
        record for record in caplog.records if record.levelno >= logging.WARNING
    ]


def test_extract_token_accepts_raw_token() -> None:
    assert ScorpionTrackClient.extract_token(" abc123 ") == "abc123"


def test_extract_token_accepts_share_url() -> None:
    assert (
        ScorpionTrackClient.extract_token(
            "https://app.scorpiontrack.com/shared/location?token=abc123"
        )
        == "abc123"
    )


def test_client_exposes_canonical_token() -> None:
    session = _FakeSession(_FakeResponse(200, {}))
    client = _client(
        session,
        " https://app.scorpiontrack.com/shared/location?token=abc123 ",
    )

    assert client.token == "abc123"


def test_extract_token_rejects_missing_query_parameter() -> None:
    with pytest.raises(ScorpionTrackInvalidTokenError):
        ScorpionTrackClient.extract_token(
            "https://app.scorpiontrack.com/shared/location"
        )


@pytest.mark.parametrize(
    "value",
    ["", "https://app.scorpiontrack.com/shared/location"],
)
def test_extract_token_expected_errors_do_not_log_warnings(
    value: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ScorpionTrackInvalidTokenError):
        ScorpionTrackClient.extract_token(value)

    _assert_safe_logs(caplog)


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
    client = _client(session)

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
@pytest.mark.parametrize(
    ("latest_position", "expected_status"),
    [
        ({"speed": "0", "ignition": "true"}, "idle"),
        ({"speed": "0", "ignition": "false"}, "parked"),
        (None, "unknown"),
    ],
)
async def test_async_get_share_sets_vehicle_status(
    latest_position: dict[str, object] | None,
    expected_status: str,
) -> None:
    vehicle: dict[str, object] = {"id": 2001}
    if latest_position is not None:
        vehicle["latest_position"] = latest_position
    payload = {"data": {"id": 101, "vehicles": [vehicle]}}
    session = _FakeSession(_FakeResponse(200, payload))

    share = await _client(session).async_get_share()

    assert share.vehicles[0].status == expected_status


@pytest.mark.asyncio
async def test_async_get_share_normalizes_invalid_and_empty_values() -> None:
    payload = {
        "data": {
            "id": 101,
            "title": "   ",
            "created_at": "not-a-timestamp",
            "expires_at": "   ",
            "vehicles": [
                {
                    "id": 2001,
                    "latest_position": {
                        "lat": "not-a-latitude",
                        "lng": "",
                        "timestamp": "not-a-timestamp",
                        "speed": [],
                        "ignition": "unknown",
                        "bearing": {"value": "not-a-bearing"},
                        "address": "   ",
                    },
                }
            ],
        }
    }
    session = _FakeSession(_FakeResponse(200, payload))

    share = await _client(session).async_get_share()
    position = share.vehicles[0].position

    assert share.title is None
    assert share.created_at is None
    assert share.expires_at is None
    assert position.latitude is None
    assert position.longitude is None
    assert position.timestamp is None
    assert position.speed_kmh is None
    assert position.ignition is None
    assert position.bearing is None
    assert position.address is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_ignition", "expected_ignition"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (1.5, True),
        (0.0, False),
        ("1", True),
        (" TRUE ", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        (" FALSE ", False),
        ("no", False),
        ("off", False),
        ("", None),
        (None, None),
        ("unknown", None),
    ],
)
async def test_async_get_share_normalizes_ignition_values(
    raw_ignition: object,
    expected_ignition: bool | None,
) -> None:
    payload = {
        "data": {
            "id": 101,
            "vehicles": [
                {
                    "id": 2001,
                    "latest_position": {"ignition": raw_ignition},
                }
            ],
        }
    }
    session = _FakeSession(_FakeResponse(200, payload))

    share = await _client(session).async_get_share()

    assert share.vehicles[0].position.ignition is expected_ignition


@pytest.mark.asyncio
async def test_async_get_share_does_not_log_token_fragments(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(_FakeResponse(200, {"data": {"id": 101, "vehicles": []}}))
    client = _client(session, SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    await client.async_get_share()

    _assert_safe_logs(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_exception"),
    [
        (401, ScorpionTrackInvalidTokenError),
        (403, ScorpionTrackInvalidTokenError),
        (404, ScorpionTrackShareUnavailableError),
        (400, ScorpionTrackConnectionError),
        (500, ScorpionTrackConnectionError),
    ],
)
async def test_http_status_exception_taxonomy_without_warning_logs(
    status: int,
    expected_exception: type[Exception],
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(_FakeResponse(status, {}))
    client = _client(session, SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(expected_exception) as exc_info:
        await client.async_get_share()

    _assert_secret_absent(_exception_chain_text(exc_info.value))
    _assert_safe_logs(caplog)


@pytest.mark.asyncio
async def test_client_error_does_not_expose_token_url_or_cause(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = _client(_FailingSession(), SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ScorpionTrackConnectionError) as exc_info:
        await client.async_get_share()

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_secret_absent(_exception_chain_text(exc_info.value))
    _assert_safe_logs(caplog)


@pytest.mark.asyncio
async def test_invalid_json_error_is_sanitized_without_warning_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(
        _FakeResponse(
            200,
            None,
            json_error=ValueError(f"Invalid JSON from {SECRET_TOKEN}"),
        )
    )
    client = _client(session, SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ScorpionTrackConnectionError) as exc_info:
        await client.async_get_share()

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_secret_absent(_exception_chain_text(exc_info.value))
    _assert_safe_logs(caplog)


@pytest.mark.asyncio
async def test_timeout_error_is_sanitized_without_warning_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(_TimeoutResponse(200, None))
    client = _client(session, SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ScorpionTrackConnectionError) as exc_info:
        await client.async_get_share()

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_secret_absent(_exception_chain_text(exc_info.value))
    _assert_safe_logs(caplog)


@pytest.mark.asyncio
async def test_async_get_share_raises_for_empty_payload() -> None:
    session = _FakeSession(_FakeResponse(200, {"data": None}))
    client = _client(session)

    with pytest.raises(ScorpionTrackShareUnavailableError):
        await client.async_get_share()


@pytest.mark.asyncio
async def test_no_active_share_remains_unavailable_without_warning_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(_FakeResponse(200, {"data": None}))
    client = _client(session, SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ScorpionTrackShareUnavailableError) as exc_info:
        await client.async_get_share()

    _assert_secret_absent(_exception_chain_text(exc_info.value))
    _assert_safe_logs(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"data": []},
        {"data": {}},
        {"data": {"id": 101}},
        {"data": {"id": SECRET_TOKEN}},
        {"data": {"id": 101, "user": [SECRET_TOKEN]}},
        {"data": {"id": 101, "vehicles": {"bad": SECRET_TOKEN}}},
        {"data": {"id": 101, "vehicles": [SECRET_TOKEN]}},
        {"data": {"id": 101, "vehicles": [{"id": SECRET_TOKEN}]}},
        {
            "data": {
                "id": 101,
                "vehicles": [{"id": 2001, "latest_position": [SECRET_TOKEN]}],
            }
        },
    ],
)
async def test_malformed_payload_schema_is_sanitized_connection_error(
    payload: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _FakeSession(_FakeResponse(200, payload))
    client = _client(session, SECRET_TOKEN)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ScorpionTrackConnectionError) as exc_info:
        await client.async_get_share()

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_secret_absent(_exception_chain_text(exc_info.value))
    _assert_safe_logs(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("distance_units", "expected_display_speed"),
    [
        ("miles", 40.4),
        ("km", 65.0),
        (None, 65.0),
    ],
)
async def test_async_get_share_keeps_api_speed_in_kmh(
    distance_units: str | None,
    expected_display_speed: float,
) -> None:
    user: dict[str, str] = {}
    if distance_units is not None:
        user["distance_units"] = distance_units
    payload = {
        "data": {
            "id": 101,
            "user": user,
            "vehicles": [
                {
                    "id": 2001,
                    "latest_position": {"speed": 65.0},
                }
            ],
        }
    }
    session = _FakeSession(_FakeResponse(200, payload))
    client = _client(session)

    share = await client.async_get_share()
    speed_kmh = share.vehicles[0].position.speed_kmh

    assert speed_kmh == 65.0
    assert share.convert_speed(speed_kmh) == expected_display_speed
    assert share.convert_speed(None) is None
