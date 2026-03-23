"""
Database Pool Manager

Manages multiple database connections to different databases on the same server.
"""

from typing import Dict, Optional

from db_manager import DatabaseManager

from utils import get_logger

logger = get_logger("db")


class DatabasePoolManager:
    """
    Manages multiple database connections.

    Allows connecting to multiple databases on the same SQL Server
    with the same credentials but different database names.
    """

    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        databases: list[str],
        port: int = 1433,
        driver: str = "ODBC Driver 18 for SQL Server",
    ):
        """
        Initialize database pool manager.

        Args:
            server: MSSQL server hostname or IP
            username: Database username
            password: Database password
            databases: List of database names to connect to
            port: Server port (default: 1433)
            driver: ODBC driver name
        """
        self.server = server
        self.username = username
        self.password = password
        self.port = port
        self.driver = driver
        self.databases = databases

        # Dictionary to store database managers
        self._managers: Dict[str, DatabaseManager] = {}

        logger.info(
            f"DatabasePoolManager initialized for {len(databases)} database(s): {', '.join(databases)}"
        )

    def connect_all(self) -> Dict[str, bool]:
        """
        Connect to all configured databases.

        Returns:
            Dictionary mapping database names to connection success status
        """
        results = {}

        for db_name in self.databases:
            logger.info(f"Connecting to database: {db_name}")

            manager = DatabaseManager(
                server=self.server,
                database=db_name,
                username=self.username,
                password=self.password,
                port=self.port,
                driver=self.driver,
            )

            success = manager.connect()
            results[db_name] = success

            if success:
                self._managers[db_name] = manager
                logger.info(f"Successfully connected to database: {db_name}")
            else:
                logger.error(f"Failed to connect to database: {db_name}")

        return results

    def disconnect_all(self):
        """Disconnect all database connections"""
        for db_name, manager in self._managers.items():
            logger.info(f"Disconnecting from database: {db_name}")
            manager.disconnect()

        self._managers.clear()
        logger.info("All database connections closed")

    def get_manager(self, database: str) -> Optional[DatabaseManager]:
        """
        Get database manager for a specific database.

        Args:
            database: Database name

        Returns:
            DatabaseManager instance or None if not connected
        """
        return self._managers.get(database)

    def is_connected(self, database: str) -> bool:
        """
        Check if a specific database is connected.

        Args:
            database: Database name

        Returns:
            True if connected, False otherwise
        """
        manager = self._managers.get(database)
        return manager is not None and manager.is_connected()

    def get_all_status(self) -> Dict[str, bool]:
        """
        Get connection status for all databases.

        Returns:
            Dictionary mapping database names to connection status
        """
        return {db_name: self.is_connected(db_name) for db_name in self.databases}

    def get_connected_databases(self) -> list[str]:
        """
        Get list of currently connected databases.

        Returns:
            List of database names that are connected
        """
        return [db_name for db_name in self.databases if self.is_connected(db_name)]

    def reconnect(self, database: str) -> bool:
        """
        Reconnect to a specific database.

        Args:
            database: Database name

        Returns:
            True if reconnection successful
        """
        manager = self._managers.get(database)
        if manager:
            logger.info(f"Reconnecting to database: {database}")
            return manager.reconnect()

        logger.error(f"Cannot reconnect - database '{database}' not found in pool")
        return False
