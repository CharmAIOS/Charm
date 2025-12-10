class CharmError(Exception):
    """Base exception for all Charm-related errors."""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error

class CharmValidationError(CharmError):
    """Raised when charm.yaml content is invalid."""
    pass

class CharmConfigError(CharmError):
    """Raised when charm.yaml is missing or entry_point is invalid."""
    pass

class CharmExecutionError(CharmError):
    """Raised when the underlying agent crashes during execution."""
    pass