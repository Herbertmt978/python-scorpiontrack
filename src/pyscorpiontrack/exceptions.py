"""Exceptions raised by pyscorpiontrack."""


class ScorpionTrackError(Exception):
    """Base exception for ScorpionTrack errors."""


class ScorpionTrackConnectionError(ScorpionTrackError):
    """Raised when the API cannot be reached."""


class ScorpionTrackInvalidTokenError(ScorpionTrackError):
    """Raised when the provided share token is invalid."""


class ScorpionTrackShareUnavailableError(ScorpionTrackError):
    """Raised when the share has expired, been revoked, or has no usable data."""
