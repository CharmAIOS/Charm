class CharmError(Exception):
    """Base exception for all Charm-related errors."""
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error

    def __str__(self):
        # 🔥 優化：如果有原始錯誤，印出原始錯誤的訊息，方便除錯
        if self.original_error:
            return f"{super().__str__()} (Caused by: {self.original_error})"
        return super().__str__()

class CharmValidationError(CharmError):
    """Raised when charm.yaml content is invalid."""
    pass

class CharmConfigError(CharmError):
    """Raised when charm.yaml is missing or entry_point is invalid."""
    pass

class CharmExecutionError(CharmError):
    """Raised when the underlying agent crashes during execution."""
    pass