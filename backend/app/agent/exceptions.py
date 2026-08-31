class PlanningError(Exception):
    """Base for all planning / agent failures."""


class ValidationFailedError(PlanningError):
    """Raised when deterministic validation cannot be repaired within the allowed attempts."""

    def __init__(self, message: str, failures: list[str]) -> None:
        super().__init__(message)
        self.failures = failures


class MaxIterationsError(PlanningError):
    """Raised when the agent loop exhausts max_iterations without producing a final response."""
