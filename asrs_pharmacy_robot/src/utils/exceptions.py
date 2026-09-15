class ASRSError(Exception):
    """Base exception for ASRS failures."""


class ConfigError(ASRSError):
    """Raised when machine configuration is invalid."""


class DatabaseError(ASRSError):
    """Raised when database operations fail."""


class GRBLError(ASRSError):
    """Raised when GRBL reports an error or cannot be reached."""


class AlarmError(GRBLError):
    """Raised when GRBL reports an alarm state."""


class SafetyError(ASRSError):
    """Raised when a requested move violates a safety rule."""

