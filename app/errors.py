"""Application-level exceptions."""


class FirmAIError(Exception):
    """Base error for all firm-ai application errors."""


class ConfigError(FirmAIError):
    """Raised when configuration cannot be loaded or is invalid."""


class HealthCheckError(FirmAIError):
    """Raised when a health check step fails unexpectedly."""


class CalculationError(FirmAIError):
    """Raised when a deterministic calculation receives invalid input."""


class DocumentError(FirmAIError):
    """Raised when a document cannot be safely ingested."""


class PdfGenerationError(FirmAIError):
    """Raised when a branded PDF cannot be safely generated or verified."""


class RetrievalError(FirmAIError):
    """Raised when retrieval cannot be safely performed."""


class ProviderError(FirmAIError):
    """Raised when a model provider call fails or returns an invalid response."""


class ContentPolicyError(FirmAIError):
    """Raised when content is outside Almond's permitted chat policy."""


class PermissionDeniedError(FirmAIError):
    """Raised when the acting user lacks permission for a requested action."""


class ApprovalRequiredError(FirmAIError):
    """Raised when an action requires human approval that has not been granted."""
