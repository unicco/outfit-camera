import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def init_database(db_enabled: bool, get_db_func: Any) -> bool:
    """データベース初期化.

    Returns:
        bool: データベースが正常に初期化されたかどうか

    """
    if not db_enabled or get_db_func is None:
        print("📁 Database disabled, using file-based storage")
        return False

    try:
        from ..automation import start_automation_services
        from ..database import check_database_connection, create_tables

        print("🔧 Initializing database...")
        create_tables()
        db_healthy = check_database_connection()

        if db_healthy:
            print("✅ Database initialized successfully")
            # Start automation services
            start_automation_services()
            print("🤖 Automation services started")
            return True
        else:
            print("⚠️ Database connection unhealthy")
            return False

    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        logger.error(f"Database initialization failed: {e}")
        return False
