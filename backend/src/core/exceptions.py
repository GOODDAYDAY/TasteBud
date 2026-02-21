"""Business exception hierarchy."""


class TasteBudError(Exception):
    """Base exception for all TasteBud errors."""


class NotFoundError(TasteBudError):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str, id: int | str) -> None:
        self.resource = resource
        self.id = id
        super().__init__(f"{resource} with id={id} not found")


class CollectorError(TasteBudError):
    """Raised when content collection fails."""


class AnalyzerError(TasteBudError):
    """Raised when content analysis fails."""


class ScoringError(TasteBudError):
    """Raised when scoring computation fails."""


class ValidationError(TasteBudError):
    """Raised when input validation fails at a domain boundary."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"Validation error on '{field}': {message}")
