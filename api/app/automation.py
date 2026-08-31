"""Automation services for daily reset and scheduled tasks
Issue #40 Phase 4: Automation features.
"""

import logging
import threading
import time
from datetime import date, datetime
from typing import Any

import schedule

from .database import SessionLocal
from .repositories import PhotoRepository
from .settings import get_settings


class DailyResetService:
    """Service for daily reset operations."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.is_running = False

    def reset_daily_capture_status(self) -> dict[str, Any]:
        """Reset daily capture status for a new day.

        Returns:
            Dictionary with reset operation results

        """
        results: dict[str, Any] = {
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "operations": {},
            "success": True,
            "errors": [],
        }

        try:
            with SessionLocal() as db:
                photo_repo = PhotoRepository(db)

                cleanup_enabled, retention_days = self._get_cleanup_settings()
                if cleanup_enabled:
                    cleaned_count = photo_repo.cleanup_old_photos(
                        keep_days=retention_days
                    )
                    results["operations"]["cleaned_old_photos"] = cleaned_count
                else:
                    results["operations"]["cleaned_old_photos"] = 0
                    self.logger.info(
                        "Photo cleanup disabled (CLEANUP_ENABLED=false). Skipping."
                    )

                self.logger.info(f"Daily reset completed successfully: {results}")

        except Exception as e:
            error_msg = f"Daily reset failed: {str(e)}"
            self.logger.error(error_msg)
            results["success"] = False
            results["errors"].append(error_msg)

        return results

    def cleanup_storage(self) -> dict[str, Any]:
        """Perform storage cleanup operations.

        Returns:
            Dictionary with cleanup operation results

        """
        results: dict[str, Any] = {
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "operations": {},
            "success": True,
            "errors": [],
        }

        try:
            with SessionLocal() as db:
                photo_repo = PhotoRepository(db)

                # Get storage stats
                storage_stats = photo_repo.get_storage_stats()
                results["operations"]["storage_stats"] = storage_stats

                cleanup_enabled, retention_days = self._get_cleanup_settings()
                if cleanup_enabled:
                    cleaned_count = photo_repo.cleanup_old_photos(
                        keep_days=retention_days
                    )
                    results["operations"]["cleaned_old_photos"] = cleaned_count
                else:
                    results["operations"]["cleaned_old_photos"] = 0
                    self.logger.info(
                        "Photo cleanup disabled (CLEANUP_ENABLED=false). Skipping."
                    )

                self.logger.info(f"Storage cleanup completed successfully: {results}")

        except Exception as e:
            error_msg = f"Storage cleanup failed: {str(e)}"
            self.logger.error(error_msg)
            results["success"] = False
            results["errors"].append(error_msg)

        return results

    def full_daily_reset(self) -> dict[str, Any]:
        """Perform full daily reset including all cleanup operations.

        Returns:
            Dictionary with all operation results

        """
        full_results: dict[str, Any] = {
            "date": date.today().isoformat(),
            "timestamp": datetime.now().isoformat(),
            "operations": {},
            "success": True,
            "errors": [],
        }

        try:
            # Reset daily capture status
            reset_results = self.reset_daily_capture_status()
            full_results["operations"]["daily_reset"] = reset_results

            if not reset_results["success"]:
                full_results["errors"].extend(reset_results["errors"])

            # Cleanup storage
            cleanup_results = self.cleanup_storage()
            full_results["operations"]["storage_cleanup"] = cleanup_results

            if not cleanup_results["success"]:
                full_results["errors"].extend(cleanup_results["errors"])

            # Overall success status
            full_results["success"] = len(full_results["errors"]) == 0

            self.logger.info(f"Full daily reset completed: {full_results}")

        except Exception as e:
            error_msg = f"Full daily reset failed: {str(e)}"
            self.logger.error(error_msg)
            full_results["success"] = False
            full_results["errors"].append(error_msg)

        return full_results

    def _get_cleanup_settings(self) -> tuple[bool, int]:
        settings = get_settings()
        return settings.cleanup_enabled, settings.photo_retention_days


class SchedulerService:
    """Service for managing scheduled tasks."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.is_running = False
        self.scheduler_thread: threading.Thread | None = None
        self.daily_reset_service = DailyResetService()

        # Configure scheduled tasks
        self._setup_schedules()

    def _setup_schedules(self) -> None:
        """Setup all scheduled tasks."""
        # Daily reset at 6:00 AM
        schedule.every().day.at("07:00").do(self._scheduled_daily_reset)

        # Storage cleanup every Sunday at 3:00 AM
        schedule.every().sunday.at("03:00").do(self._scheduled_storage_cleanup)

        # Log cleanup every day at 2:00 AM
        schedule.every().day.at("02:00").do(self._scheduled_log_cleanup)

        self.logger.info("Scheduled tasks configured")

    def start(self) -> None:
        """Start the scheduler service."""
        if self.is_running:
            self.logger.warning("Scheduler service is already running")
            return

        self.is_running = True
        self.scheduler_thread = threading.Thread(
            target=self._run_scheduler, daemon=True
        )
        self.scheduler_thread.start()

        self.logger.info("Scheduler service started")

    def stop(self) -> None:
        """Stop the scheduler service."""
        if not self.is_running:
            return

        self.is_running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)

        schedule.clear()
        self.logger.info("Scheduler service stopped")

    def _run_scheduler(self) -> None:
        """Main scheduler loop."""
        self.logger.info("Scheduler loop started")

        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                self.logger.error(f"Scheduler error: {e}")
                time.sleep(60)

        self.logger.info("Scheduler loop stopped")

    def _scheduled_daily_reset(self) -> None:
        """Scheduled daily reset task."""
        try:
            self.logger.info("Running scheduled daily reset")
            results = self.daily_reset_service.full_daily_reset()

            if results["success"]:
                self.logger.info("Scheduled daily reset completed successfully")
            else:
                self.logger.error(
                    f"Scheduled daily reset had errors: {results['errors']}"
                )

        except Exception as e:
            self.logger.error(f"Scheduled daily reset failed: {e}")

    def _scheduled_storage_cleanup(self) -> None:
        """Scheduled storage cleanup task."""
        try:
            self.logger.info("Running scheduled storage cleanup")
            results = self.daily_reset_service.cleanup_storage()

            if results["success"]:
                self.logger.info("Scheduled storage cleanup completed successfully")
            else:
                self.logger.error(
                    f"Scheduled storage cleanup had errors: {results['errors']}"
                )

        except Exception as e:
            self.logger.error(f"Scheduled storage cleanup failed: {e}")

    def _scheduled_log_cleanup(self) -> None:
        """Scheduled log cleanup task."""
        try:
            self.logger.info("Running scheduled log cleanup")

            # Log cleanup disabled for now (no system_logs table in simplified schema)
            self.logger.info("Log cleanup skipped - using simplified schema")

        except Exception as e:
            self.logger.error(f"Scheduled log cleanup failed: {e}")

    def get_next_runs(self) -> dict[str, Any]:
        """Get information about next scheduled runs."""
        try:
            jobs_info = []

            for job in schedule.jobs:
                next_run = job.next_run
                jobs_info.append(
                    {
                        "function": getattr(job.job_func, "__name__", "unknown"),
                        "next_run": next_run.isoformat() if next_run else None,
                        "interval": str(job.unit),
                        "at_time": str(job.at_time) if job.at_time else None,
                        "tags": list(job.tags) if job.tags else [],
                    }
                )

            return {
                "scheduler_running": self.is_running,
                "jobs": jobs_info,
                "total_jobs": len(jobs_info),
            }

        except Exception as e:
            self.logger.error(f"Failed to get next runs info: {e}")
            return {"error": str(e)}

    def trigger_manual_reset(self) -> dict[str, Any]:
        """Manually trigger daily reset operation."""
        try:
            self.logger.info("Manual daily reset triggered")
            results = self.daily_reset_service.full_daily_reset()

            # Manual trigger logged
            self.logger.info(f"Manual daily reset results: {results}")

            return results

        except Exception as e:
            error_msg = f"Manual daily reset failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "timestamp": datetime.now().isoformat(),
            }


# Global scheduler service instance
scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    """Get or create the global scheduler service instance."""
    global scheduler_service

    if scheduler_service is None:
        scheduler_service = SchedulerService()

    return scheduler_service


def start_automation_services() -> None:
    """Start all automation services."""
    try:
        scheduler = get_scheduler_service()
        scheduler.start()
        logging.getLogger(__name__).info("Automation services started")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to start automation services: {e}")


def stop_automation_services() -> None:
    """Stop all automation services."""
    try:
        global scheduler_service
        if scheduler_service:
            scheduler_service.stop()
            scheduler_service = None
        logging.getLogger(__name__).info("Automation services stopped")
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to stop automation services: {e}")
