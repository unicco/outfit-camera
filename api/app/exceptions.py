"""Custom exceptions for dependency injection."""

from fastapi import HTTPException


class DependencyInitializationError(Exception):
    """Raised when a dependency fails to initialize."""

    def __init__(self, service_name: str, original_error: Exception):
        self.service_name = service_name
        self.original_error = original_error
        super().__init__(f"Failed to initialize {service_name}: {str(original_error)}")


class ServiceUnavailableError(HTTPException):
    """Raised when a required service is unavailable."""

    def __init__(self, service_name: str):
        super().__init__(
            status_code=503,
            detail=f"Service temporarily unavailable: {service_name}. Please try again later.",
        )


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""

    pass
