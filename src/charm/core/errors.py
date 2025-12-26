from typing import Optional


class CharmError(Exception):
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error

    def __str__(self):
        if self.original_error:
            return f"{super().__str__()} (Caused by: {self.original_error})"
        return super().__str__()


class CharmValidationError(CharmError):
    """Raised when uac/yaml validation fails."""

    pass


class CharmConfigError(CharmError):
    """Raised when configuration or imports are missing."""

    pass


class CharmExecutionError(CharmError):
    """Raised when the agent crashes during runtime."""

    pass
