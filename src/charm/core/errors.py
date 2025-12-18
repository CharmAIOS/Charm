class CharmError(Exception):
    def __init__(self, message: str, original_error: Exception = None):
        super().__init__(message)
        self.original_error = original_error

    def __str__(self):
        if self.original_error:
            return f"{super().__str__()} (Caused by: {self.original_error})"
        return super().__str__()

class CharmValidationError(CharmError):
    pass

class CharmConfigError(CharmError):
    pass

class CharmExecutionError(CharmError):
    pass