"""
Database Pool Manager

Manages connection pools for multiple databases on the same server.
Each database has its own pool of connections for concurrent request handling.
"""

import queue
import threading
import time
from contextlib import contextmanager
from typing import Dict, Optional

from db_manager import DatabaseManager

from utils import get_logger

logger = get_logger("db")


class ConnectionPool:
    """
    Thread-safe connection pool for a single database.

    Manages a pool of DatabaseManager connections with automatic
    health checking and connection recycling.
    """

    def __init__(
        self,
        database: str,
        server: str,
        username: str,
        password: str,
        port: int,
        driver: str,
        pool_size: int = 5,
        max_idle_time: int = 3600,
    ):
        """
        Initialize connection pool for a database.

        Args:
            database: Database name
            server: MSSQL server hostname or IP
            username: Database username
            password: Database password
            port: Server port
            driver: ODBC driver name
            pool_size: Number of connections in the pool (default: 5)
            max_idle_time: Maximum idle time in seconds before recycling (default: 3600)
        """
        self.database = database
        self.server = server
        self.username = username
        self.password = password
        self.port = port
        self.driver = driver
        self.pool_size = pool_size
        self.max_idle_time = max_idle_time

        # Thread-safe queue for available connections
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        self._all_connections: Dict[int, Dict] = (
            {}
        )  # Track all connections with metadata
        self._lock = threading.Lock()
        self._connection_counter = 0
        self._closed = False

        logger.info(
            f"Connection pool initialized for '{database}' with size {pool_size}"
        )

    def _create_connection(self) -> DatabaseManager:
        """Create a new database connection."""
        manager = DatabaseManager(
            server=self.server,
            database=self.database,
            username=self.username,
            password=self.password,
            port=self.port,
            driver=self.driver,
        )
        if not manager.connect():
            raise Exception(
                f"Failed to create connection to database '{self.database}'"
            )

        with self._lock:
            conn_id = self._connection_counter
            self._connection_counter += 1
            self._all_connections[conn_id] = {
                "manager": manager,
                "created_at": time.time(),
                "last_used": time.time(),
            }

        logger.debug(f"Created new connection {conn_id} for '{self.database}'")
        return manager

    def initialize(self) -> bool:
        """
        Initialize the pool with connections.

        Returns:
            True if all connections created successfully
        """
        try:
            for i in range(self.pool_size):
                manager = self._create_connection()
                self._pool.put(manager)
                logger.debug(
                    f"Added connection {i+1}/{self.pool_size} to pool for '{self.database}'"
                )

            logger.info(
                f"Connection pool for '{self.database}' initialized with {self.pool_size} connections"
            )
            return True
        except Exception as e:
            logger.error(
                f"Failed to initialize connection pool for '{self.database}': {str(e)}"
            )
            return False

    @contextmanager
    def get_connection(self, timeout: float = 30.0):
        """
        Get a connection from the pool (context manager).

        Args:
            timeout: Maximum time to wait for a connection (seconds)

        Yields:
            DatabaseManager: Connection from the pool

        Raises:
            queue.Empty: If no connection available within timeout
            Exception: If pool is closed
        """
        if self._closed:
            raise Exception(f"Connection pool for '{self.database}' is closed")

        manager = None
        try:
            # Get connection from pool with timeout
            manager = self._pool.get(timeout=timeout)

            # Update last used time
            with self._lock:
                for conn_id, conn_info in self._all_connections.items():
                    if conn_info["manager"] is manager:
                        conn_info["last_used"] = time.time()
                        break

            # Check if connection is still valid
            if not manager.is_connected():
                logger.warning(f"Connection to '{self.database}' lost, reconnecting...")
                if not manager.reconnect():
                    # Connection failed, create a new one
                    logger.error(
                        f"Reconnection failed for '{self.database}', creating new connection"
                    )
                    manager = self._create_connection()

            yield manager

        finally:
            # Return connection to pool
            if manager is not None:
                try:
                    self._pool.put(manager, block=False)
                except queue.Full:
                    logger.warning(
                        f"Pool full when returning connection to '{self.database}'"
                    )

    def health_check(self) -> Dict[str, any]:
        """
        Perform health check on all connections in the pool.

        Returns:
            Dictionary with health statistics
        """
        with self._lock:
            total = len(self._all_connections)
            healthy = 0
            stale = 0
            current_time = time.time()

            for conn_id, conn_info in self._all_connections.items():
                manager = conn_info["manager"]
                if manager.is_connected():
                    healthy += 1

                # Check if connection is idle for too long
                idle_time = current_time - conn_info["last_used"]
                if idle_time > self.max_idle_time:
                    stale += 1

            return {
                "database": self.database,
                "total_connections": total,
                "healthy_connections": healthy,
                "stale_connections": stale,
                "available_in_pool": self._pool.qsize(),
            }

    def close_all(self):
        """Close all connections in the pool."""
        if self._closed:
            return

        self._closed = True

        # Close all connections
        with self._lock:
            for conn_id, conn_info in self._all_connections.items():
                try:
                    manager = conn_info["manager"]
                    manager.disconnect()
                    logger.debug(f"Closed connection {conn_id} for '{self.database}'")
                except Exception as e:
                    logger.error(
                        f"Error closing connection {conn_id} for '{self.database}': {str(e)}"
                    )

            self._all_connections.clear()

        # Clear the queue
        while not self._pool.empty():
            try:
                self._pool.get_nowait()
            except queue.Empty:
                break

        logger.info(f"Connection pool for '{self.database}' closed")


class DatabasePoolManager:
    """
    Manages connection pools for multiple databases.

    Each database gets its own connection pool with configurable size.
    Provides thread-safe access to database connections.
    """

    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        databases: list[str],
        port: int = 1433,
        driver: str = "ODBC Driver 18 for SQL Server",
        pool_size_per_db: int = 5,
    ):
        """
        Initialize database pool manager with connection pooling.

        Args:
            server: MSSQL server hostname or IP
            username: Database username
            password: Database password
            databases: List of database names to connect to
            port: Server port (default: 1433)
            driver: ODBC driver name
            pool_size_per_db: Number of connections per database (default: 5)
        """
        self.server = server
        self.username = username
        self.password = password
        self.port = port
        self.driver = driver
        self.databases = databases
        self.pool_size_per_db = pool_size_per_db

        # Dictionary to store connection pools
        self._pools: Dict[str, ConnectionPool] = {}

        logger.info(
            f"DatabasePoolManager initialized for {len(databases)} database(s) "
            f"with {pool_size_per_db} connections each: {', '.join(databases)}"
        )

    def connect_all(self) -> Dict[str, bool]:
        """
        Create and initialize connection pools for all configured databases.

        Returns:
            Dictionary mapping database names to initialization success status
        """
        results = {}

        for db_name in self.databases:
            logger.info(f"Initializing connection pool for database: {db_name}")

            pool = ConnectionPool(
                database=db_name,
                server=self.server,
                username=self.username,
                password=self.password,
                port=self.port,
                driver=self.driver,
                pool_size=self.pool_size_per_db,
            )

            success = pool.initialize()
            results[db_name] = success

            if success:
                self._pools[db_name] = pool
                logger.info(
                    f"Successfully initialized connection pool for database: {db_name}"
                )
            else:
                logger.error(
                    f"Failed to initialize connection pool for database: {db_name}"
                )

        return results

    def disconnect_all(self):
        """Close all connection pools"""
        for db_name, pool in self._pools.items():
            logger.info(f"Closing connection pool for database: {db_name}")
            pool.close_all()

        self._pools.clear()
        logger.info("All connection pools closed")

    def get_connection(self, database: str, timeout: float = 30.0):
        """
        Get a connection from the pool for a specific database (context manager).

        Args:
            database: Database name
            timeout: Maximum time to wait for connection (seconds)

        Returns:
            Context manager yielding DatabaseManager

        Raises:
            ValueError: If database not found in pool
            queue.Empty: If no connection available within timeout
        """
        pool = self._pools.get(database)
        if pool is None:
            raise ValueError(f"Database '{database}' not found in connection pool")

        return pool.get_connection(timeout)

    def get_manager(self, database: str) -> Optional["PooledDatabaseManager"]:
        """
        Get a pooled database manager wrapper for a specific database.

        This provides backward compatibility with the old interface
        while using connection pooling internally.

        Args:
            database: Database name

        Returns:
            PooledDatabaseManager instance or None if not found
        """
        pool = self._pools.get(database)
        if pool is None:
            return None

        return PooledDatabaseManager(pool)

    def is_connected(self, database: str) -> bool:
        """
        Check if a specific database pool exists and is healthy.

        Args:
            database: Database name

        Returns:
            True if pool exists and has healthy connections
        """
        pool = self._pools.get(database)
        if pool is None:
            return False

        health = pool.health_check()
        return health["healthy_connections"] > 0

    def get_all_status(self) -> Dict[str, bool]:
        """
        Get connection status for all databases.

        Returns:
            Dictionary mapping database names to connection status
        """
        return {db_name: self.is_connected(db_name) for db_name in self.databases}

    def get_connected_databases(self) -> list[str]:
        """
        Get list of databases with healthy connection pools.

        Returns:
            List of database names that have healthy connections
        """
        return [db_name for db_name in self.databases if self.is_connected(db_name)]

    def get_health_stats(self) -> Dict[str, Dict]:
        """
        Get detailed health statistics for all connection pools.

        Returns:
            Dictionary mapping database names to health statistics
        """
        stats = {}
        for db_name, pool in self._pools.items():
            stats[db_name] = pool.health_check()
        return stats

    def reconnect(self, database: str) -> bool:
        """
        Reconnect is not applicable with connection pooling.
        Individual connections reconnect automatically as needed.

        Args:
            database: Database name

        Returns:
            True if pool exists
        """
        logger.warning(
            f"Reconnect called for '{database}' - with connection pooling, "
            "individual connections reconnect automatically"
        )
        return database in self._pools


class PooledDatabaseManager:
    """
    Wrapper that provides DatabaseManager-like interface using connection pooling.

    This class provides backward compatibility for code expecting a DatabaseManager
    instance, but uses connection pooling internally.
    """

    def __init__(self, pool: ConnectionPool):
        """
        Initialize pooled database manager.

        Args:
            pool: ConnectionPool to use for database operations
        """
        self.pool = pool
        self.database = pool.database

    def execute_stored_procedure(
        self,
        procedure_name: str,
        parameters: Dict = None,
        output_params: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Execute a stored procedure using a connection from the pool.

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of input parameter names and values
            output_params: Dictionary of output parameter names and SQL types

        Returns:
            Dict with execution results
        """
        try:
            with self.pool.get_connection() as manager:
                return manager.execute_stored_procedure(
                    procedure_name=procedure_name,
                    parameters=parameters,
                    output_params=output_params,
                )
        except queue.Empty:
            logger.error(f"Timeout waiting for connection to '{self.database}'")
            return {
                "success": False,
                "error": "Connection pool timeout - no connections available",
                "affected_rows": 0,
                "output_values": {},
            }
        except Exception as e:
            logger.error(
                f"Error executing procedure on '{self.database}': {str(e)}",
                exc_info=True,
            )
            return {
                "success": False,
                "error": str(e),
                "affected_rows": 0,
                "output_values": {},
            }

    def execute_query_procedure(
        self,
        procedure_name: str,
        parameters: Dict = None,
        output_params: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        Execute a query procedure using a connection from the pool.

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of input parameter names and values
            output_params: Dictionary of output parameter names and SQL types

        Returns:
            Dict with query results
        """
        try:
            with self.pool.get_connection() as manager:
                return manager.execute_query_procedure(
                    procedure_name=procedure_name,
                    parameters=parameters,
                    output_params=output_params,
                )
        except queue.Empty:
            logger.error(f"Timeout waiting for connection to '{self.database}'")
            return {
                "success": False,
                "error": "Connection pool timeout - no connections available",
                "data": [],
                "output_values": {},
            }
        except Exception as e:
            logger.error(
                f"Error executing query on '{self.database}': {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "output_values": {},
            }

    def is_connected(self) -> bool:
        """
        Check if the connection pool is healthy.

        Returns:
            True if pool has healthy connections
        """
        health = self.pool.health_check()
        return health["healthy_connections"] > 0
