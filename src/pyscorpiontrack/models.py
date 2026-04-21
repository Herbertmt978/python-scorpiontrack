"""Typed data models returned by pyscorpiontrack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class ScorpionTrackPosition:
    """The latest known position for a vehicle."""

    latitude: float | None
    longitude: float | None
    timestamp: datetime | None
    speed_kmh: float | None
    ignition: bool | None
    bearing: float | None
    address: str | None


@dataclass(slots=True, frozen=True)
class ScorpionTrackVehicle:
    """A shared ScorpionTrack vehicle."""

    id: int
    name: str | None
    registration: str | None
    make: str | None
    model: str | None
    position: ScorpionTrackPosition
    status: str

    @property
    def display_name(self) -> str:
        """Return the best user-facing name for the vehicle."""
        return self.registration or self.name or f"Vehicle {self.id}"


@dataclass(slots=True, frozen=True)
class ScorpionTrackShare:
    """A shared location bundle."""

    id: int
    token: str
    title: str | None
    owner_name: str | None
    distance_units: str
    created_at: datetime | None
    expires_at: datetime | None
    vehicles: tuple[ScorpionTrackVehicle, ...]

    @property
    def uses_miles(self) -> bool:
        """Return True if the share prefers imperial distance units."""
        return self.distance_units.lower() == "miles"

    def convert_speed(self, speed_kmh: float | None) -> float | None:
        """Convert API speed to the share's preferred unit."""
        if speed_kmh is None:
            return None
        if self.uses_miles:
            return round(speed_kmh * 0.621371, 1)
        return round(speed_kmh, 1)
