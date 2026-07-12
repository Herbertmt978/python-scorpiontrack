"""Async client for ScorpionTrack shared-location links."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from aiohttp import ClientError, ClientSession

from .exceptions import (
    ScorpionTrackConnectionError,
    ScorpionTrackInvalidTokenError,
    ScorpionTrackShareUnavailableError,
)
from .models import (
    ScorpionTrackPosition,
    ScorpionTrackShare,
    ScorpionTrackVehicle,
)

API_BASE_URL = "https://api2.fleet.scorpiontrack.com/v1"


class ScorpionTrackClient:
    """Minimal client for the shared-location endpoint."""

    def __init__(
        self,
        session: ClientSession,
        token: str,
        *,
        base_url: str = API_BASE_URL,
        timeout_seconds: int = 10,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._token = self.extract_token(token)
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def token(self) -> str:
        """Return the canonical share token."""
        return self._token

    @staticmethod
    def extract_token(value: str) -> str:
        """Extract a ScorpionTrack token from a raw token or shared URL."""
        cleaned = value.strip()
        if not cleaned:
            raise ScorpionTrackInvalidTokenError("No share token supplied")

        if "://" not in cleaned:
            return cleaned

        parsed = urlparse(cleaned)
        token = parse_qs(parsed.query).get("token", [None])[0]
        if not token:
            raise ScorpionTrackInvalidTokenError(
                "Shared URL does not contain a token parameter"
            )

        return token.strip()

    async def async_get_share(self) -> ScorpionTrackShare:
        """Fetch the latest shared-location payload."""
        url = f"{self._base_url}/location-shares/{quote(self._token, safe='')}/view"
        request_error: ScorpionTrackConnectionError | None = None

        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._session.get(url) as response:
                    if response.status in (401, 403):
                        raise ScorpionTrackInvalidTokenError("Share token was rejected")
                    if response.status == 404:
                        raise ScorpionTrackShareUnavailableError(
                            "Shared location was not found"
                        )
                    if response.status >= 400:
                        raise ScorpionTrackConnectionError(
                            f"Unexpected HTTP status {response.status}"
                        )

                    payload = await response.json(content_type=None)
        except TimeoutError:
            request_error = ScorpionTrackConnectionError(
                "Timed out contacting ScorpionTrack"
            )
        except ClientError:
            request_error = ScorpionTrackConnectionError(
                "Failed to contact ScorpionTrack"
            )
        except ValueError:
            request_error = ScorpionTrackConnectionError(
                "ScorpionTrack returned invalid JSON"
            )

        # Avoid retaining URL-bearing request exceptions as context.
        if request_error is not None:
            raise request_error

        try:
            return self._parse_share(payload)
        except (AttributeError, KeyError, TypeError, ValueError):
            pass

        # Parsing errors can contain values from the response payload.
        raise ScorpionTrackConnectionError(
            "ScorpionTrack returned malformed shared-location data"
        )

    def _parse_share(self, payload: object) -> ScorpionTrackShare:
        """Convert the API payload into structured data."""
        if not isinstance(payload, dict):
            raise TypeError("Payload is not an object")
        if "data" not in payload:
            raise KeyError("data")

        share_data = payload["data"]
        if share_data is None:
            raise ScorpionTrackShareUnavailableError(
                "Shared location is expired, revoked, or empty"
            )
        if not isinstance(share_data, dict):
            raise TypeError("Share data is not an object")

        user_data = share_data.get("user")
        if user_data is None:
            user: dict[str, Any] = {}
        elif isinstance(user_data, dict):
            user = user_data
        else:
            raise TypeError("Share user is not an object")
        owner_name = (
            " ".join(
                part for part in (user.get("first_name"), user.get("last_name")) if part
            )
            or None
        )

        if "vehicles" not in share_data:
            raise KeyError("vehicles")
        vehicles_data = share_data["vehicles"]
        if not isinstance(vehicles_data, list):
            raise TypeError("Share vehicles is not a list")
        vehicles: list[ScorpionTrackVehicle] = []
        for vehicle_data in vehicles_data:
            if not isinstance(vehicle_data, dict):
                raise TypeError("Share vehicle is not an object")
            vehicles.append(self._parse_vehicle(vehicle_data))

        return ScorpionTrackShare(
            id=int(share_data["id"]),
            token=str(share_data.get("token") or self._token),
            title=_clean_text(share_data.get("title")),
            owner_name=owner_name,
            distance_units=str(user.get("distance_units") or "km"),
            created_at=_parse_datetime(share_data.get("created_at")),
            expires_at=_parse_datetime(share_data.get("expires_at"), assume_utc=True),
            vehicles=tuple(vehicles),
        )

    def _parse_vehicle(self, vehicle_data: dict[str, Any]) -> ScorpionTrackVehicle:
        """Parse a shared vehicle."""
        latest_position_data = vehicle_data.get("latest_position")
        if latest_position_data is None:
            latest_position: dict[str, Any] = {}
        elif isinstance(latest_position_data, dict):
            latest_position = latest_position_data
        else:
            raise TypeError("Latest position is not an object")
        position = ScorpionTrackPosition(
            latitude=_to_float(latest_position.get("lat")),
            longitude=_to_float(latest_position.get("lng")),
            timestamp=_parse_datetime(latest_position.get("timestamp")),
            speed_kmh=_to_float(latest_position.get("speed")),
            ignition=_to_bool(latest_position.get("ignition")),
            bearing=_to_float(latest_position.get("bearing")),
            address=_clean_text(latest_position.get("address")),
        )

        status = "unknown"
        if position.speed_kmh is not None and position.speed_kmh > 0:
            status = "moving"
        elif position.ignition is True:
            status = "idle"
        elif latest_position:
            status = "parked"

        return ScorpionTrackVehicle(
            id=int(vehicle_data["id"]),
            name=_clean_text(vehicle_data.get("name")),
            registration=_clean_text(vehicle_data.get("registration")),
            make=_clean_text(vehicle_data.get("make")),
            model=_clean_text(vehicle_data.get("model")),
            position=position,
            status=status,
        )


def _clean_text(value: Any) -> str | None:
    """Normalize text values."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _to_float(value: Any) -> float | None:
    """Convert a value to float when possible."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    """Convert a value to bool when possible."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _parse_datetime(value: Any, *, assume_utc: bool = False) -> datetime | None:
    """Parse an ISO-style datetime from the API."""
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if assume_utc and "Z" not in text and "+" not in text:
        text = f"{text}Z"

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
