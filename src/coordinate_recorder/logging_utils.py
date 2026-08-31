"""Logging utilities for Coordinate Recorder system."""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "service": getattr(record, "service", "unknown"),
            "component": getattr(record, "component", record.name),
            "filename": record.filename,
            "line_number": record.lineno,
            "function": record.funcName,
        }

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            # Convert numpy types to Python native types
            extra_fields = {}
            for key, value in record.extra_fields.items():
                if hasattr(value, "item"):  # numpy scalar
                    extra_fields[key] = value.item()
                elif hasattr(value, "tolist"):  # numpy array
                    extra_fields[key] = value.tolist()
                else:
                    extra_fields[key] = value
            log_data.update(extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(
    service_name: str,
    component: str = "main",
    log_level: str = "INFO",
    log_file: str | None = None,
) -> logging.Logger:
    """Set up structured logging.

    Args:
        service_name: Name of the service (e.g., 'backend', 'camera')
        component: Component within service (e.g., 'api', 'detection')
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path

    Returns:
        Configured logger instance

    """
    logger = logging.getLogger(f"{service_name}.{component}")

    # Clear existing handlers
    logger.handlers.clear()
    logger.setLevel(getattr(logging, log_level.upper()))

    # Console handler with structured format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredFormatter())
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(StructuredFormatter())
        logger.addHandler(file_handler)

    # Add service and component as default extra fields
    class ServiceContextFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.service = service_name
            record.component = component
            return True

    logger.addFilter(ServiceContextFilter())

    return logger


def log_with_context(
    logger: logging.Logger, level: str, message: str, **context: Any
) -> None:
    """Log message with additional context fields.

    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error)
        message: Log message
        **context: Additional context fields

    """
    extra = {"extra_fields": context}
    getattr(logger, level.lower())(message, extra=extra)


def setup_backend_logging() -> logging.Logger:
    """Set up logging for backend service."""
    log_dir = os.getenv("BACKEND_LOG_DIR", "/var/log/coordinate-recorder")
    return setup_logging(
        service_name="backend",
        component="api",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=f"{log_dir}/backend.log",
    )


def setup_camera_logging(camera_mode: str = "unknown") -> logging.Logger:
    """Set up logging for camera service."""
    logger = setup_logging(
        service_name="camera",
        component="capture",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file="/var/log/camera-service/camera.log",
    )

    # Add camera mode context
    class CameraModeFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.camera_mode = camera_mode
            return True

    logger.addFilter(CameraModeFilter())
    return logger


# Convenience functions for common logging patterns
def log_api_request(
    logger: logging.Logger, method: str, path: str, status_code: int, duration_ms: float
) -> None:
    """Log API request with structured data."""
    log_with_context(
        logger,
        "info",
        f"{method} {path} -> {status_code}",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        request_type="api",
    )


def log_camera_capture(
    logger: logging.Logger,
    success: bool,
    filename: str | None = None,
    error: str | None = None,
) -> None:
    """Log camera capture event."""
    if success:
        log_with_context(
            logger,
            "info",
            f"Photo captured successfully: {filename}",
            capture_success=True,
            filename=filename,
            event_type="capture",
        )
    else:
        log_with_context(
            logger,
            "error",
            f"Photo capture failed: {error}",
            capture_success=False,
            error=error,
            event_type="capture",
        )


def log_detection_result(
    logger: logging.Logger,
    person_detected: bool,
    clothing_items: list[str],
    confidence: float | None = None,
) -> None:
    """Log object detection result."""
    log_with_context(
        logger,
        "info",
        f"Detection completed: person={person_detected}, items={len(clothing_items)}",
        person_detected=person_detected,
        clothing_items_count=len(clothing_items),
        clothing_items=clothing_items,
        confidence=confidence,
        event_type="detection",
    )


def log_person_proximity(
    logger: logging.Logger,
    is_nearby: bool,
    confidence: float,
    person_count: int,
    size_ratio: float,
) -> None:
    """Log person proximity detection result."""
    log_with_context(
        logger,
        "debug" if not is_nearby else "info",
        f"Person proximity: nearby={is_nearby}, confidence={confidence:.3f}",
        is_person_nearby=is_nearby,
        person_confidence=confidence,
        person_count=person_count,
        largest_size_ratio=size_ratio,
        event_type="proximity_detection",
    )


def log_display_control(
    logger: logging.Logger,
    action: str,
    success: bool,
    reason: str,
    display_on: bool,
) -> None:
    """Log display control action."""
    level = "info" if success else "error"
    log_with_context(
        logger,
        level,
        f"Display {action}: {('successful' if success else 'failed')} - {reason}",
        display_action=action,
        display_success=success,
        display_on=display_on,
        reason=reason,
        event_type="display_control",
    )


def log_person_display_state(
    logger: logging.Logger,
    person_present: bool,
    display_on: bool,
    time_since_last_person: float | None = None,
    time_since_last_operation: float | None = None,
) -> None:
    """Log person display controller state."""
    log_with_context(
        logger,
        "debug",
        f"State: person={person_present}, display={display_on}",
        person_present=person_present,
        display_on=display_on,
        time_since_last_person=time_since_last_person,
        time_since_last_operation=time_since_last_operation,
        event_type="state_monitoring",
    )


def setup_person_display_logging() -> logging.Logger:
    """Set up logging for person display controller."""
    log_dir = os.getenv("LOG_DIR", "logs")
    return setup_logging(
        service_name="person_display",
        component="controller",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=f"{log_dir}/person_display.log",
    )
