"""
Database Manager Module

Handles MSSQL database connections and stored procedure execution.
"""

import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional

import pyodbc

from utils import get_logger

logger = get_logger("db")


class DatabaseManager:
    """
    Manages MSSQL database connections and operations.

    This class handles connection pooling, stored procedure execution,
    and error handling for MSSQL database operations.
    """

    def __init__(
        self,
        server: str,
        database: str,
        username: str,
        password: str,
        port: int = 1433,
        driver: str = "ODBC Driver 18 for SQL Server",
    ):
        """
        Initialize database manager with connection parameters.

        Args:
            server: MSSQL server hostname or IP
            database: Database name
            username: Database username
            password: Database password
            port: Server port (default: 1433)
            driver: ODBC driver name
        """
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.port = port
        self.driver = driver

        self._connection: Optional[pyodbc.Connection] = None
        self._lock = threading.Lock()

        logger.info(f"DatabaseManager initialized for {server}:{port}/{database}")

    def _build_connection_string(self) -> str:
        """Build ODBC connection string"""
        return (
            f"DRIVER={{{self.driver}}};"
            f"SERVER={self.server},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=30;"
        )

    def connect(self) -> bool:
        """
        Establish database connection.

        Returns:
            bool: True if connection successful, False otherwise
        """
        with self._lock:
            try:
                if self._connection is not None:
                    logger.warning("Connection already exists, closing old connection")
                    self._connection.close()

                connection_string = self._build_connection_string()
                logger.info("Attempting to connect to database...")

                self._connection = pyodbc.connect(connection_string, timeout=30)
                self._connection.autocommit = False  # Use explicit transactions

                logger.info("Database connection established successfully")
                return True

            except pyodbc.Error as e:
                logger.error(f"Database connection failed: {str(e)}", exc_info=True)
                self._connection = None
                return False
            except Exception as e:
                logger.error(
                    f"Unexpected error during connection: {str(e)}", exc_info=True
                )
                self._connection = None
                return False

    def disconnect(self):
        """Close database connection"""
        with self._lock:
            if self._connection:
                try:
                    self._connection.close()
                    logger.info("Database connection closed")
                except Exception as e:
                    logger.error(f"Error closing connection: {str(e)}")
                finally:
                    self._connection = None

    def is_connected(self) -> bool:
        """
        Check if database connection is active.

        Returns:
            bool: True if connected, False otherwise
        """
        if self._connection is None:
            return False

        try:
            # Test connection with a simple query
            cursor = self._connection.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except:
            return False

    def reconnect(self) -> bool:
        """
        Reconnect to database.

        Returns:
            bool: True if reconnection successful
        """
        logger.info("Attempting to reconnect to database...")
        self.disconnect()
        return self.connect()

    @contextmanager
    def get_cursor(self):
        """
        Context manager for database cursor.

        Yields:
            pyodbc.Cursor: Database cursor

        Raises:
            Exception: If connection is not established
        """
        if not self.is_connected():
            logger.warning("Connection lost, attempting to reconnect...")
            if not self.reconnect():
                raise Exception("Database connection not available")

        cursor = self._connection.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def execute_stored_procedure(
        self, procedure_name: str, parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure (for INSERT, UPDATE, DELETE operations).

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dict with keys:
                - success (bool): Whether execution was successful
                - affected_rows (int): Number of rows affected
                - error (str): Error message if failed
        """
        parameters = parameters or {}

        try:
            with self.get_cursor() as cursor:
                # Build parameter placeholders
                param_list = list(parameters.values())
                placeholders = ", ".join(["?" for _ in param_list])

                # Execute stored procedure
                sql = (
                    f"EXEC {procedure_name} {placeholders}"
                    if placeholders
                    else f"EXEC {procedure_name}"
                )

                logger.debug(f"Executing: {sql} with parameters: {param_list}")

                cursor.execute(sql, param_list)
                affected_rows = cursor.rowcount

                # Commit transaction
                self._connection.commit()

                logger.info(
                    f"Stored procedure executed: {procedure_name}, affected rows: {affected_rows}"
                )

                return {"success": True, "affected_rows": affected_rows}

        except pyodbc.Error as e:
            logger.error(f"Database error in {procedure_name}: {str(e)}", exc_info=True)
            try:
                self._connection.rollback()
            except:
                pass
            return {"success": False, "error": str(e), "affected_rows": 0}
        except Exception as e:
            logger.error(
                f"Unexpected error in {procedure_name}: {str(e)}", exc_info=True
            )
            try:
                self._connection.rollback()
            except:
                pass
            return {"success": False, "error": str(e), "affected_rows": 0}

    def execute_query_procedure(
        self, procedure_name: str, parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure that returns data (SELECT operations).

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dict with keys:
                - success (bool): Whether execution was successful
                - data (List[Dict]): List of rows as dictionaries
                - error (str): Error message if failed
        """
        parameters = parameters or {}

        try:
            with self.get_cursor() as cursor:
                # Build parameter placeholders
                param_list = list(parameters.values())
                placeholders = ", ".join(["?" for _ in param_list])

                # Execute stored procedure
                sql = (
                    f"EXEC {procedure_name} {placeholders}"
                    if placeholders
                    else f"EXEC {procedure_name}"
                )

                logger.debug(f"Executing query: {sql} with parameters: {param_list}")

                cursor.execute(sql, param_list)

                # Fetch all results
                columns = (
                    [column[0] for column in cursor.description]
                    if cursor.description
                    else []
                )
                results = []

                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))

                logger.info(
                    f"Query procedure executed: {procedure_name}, returned {len(results)} rows"
                )

                return {"success": True, "data": results}

        except pyodbc.Error as e:
            logger.error(f"Database error in {procedure_name}: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e), "data": []}
        except Exception as e:
            logger.error(
                f"Unexpected error in {procedure_name}: {str(e)}", exc_info=True
            )
            return {"success": False, "error": str(e), "data": []}

    def execute_scalar_procedure(
        self, procedure_name: str, parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure that returns a single value.

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dict with keys:
                - success (bool): Whether execution was successful
                - value (Any): The scalar value returned
                - error (str): Error message if failed
        """
        result = self.execute_query_procedure(procedure_name, parameters)

        if result["success"] and result["data"]:
            # Get first column of first row
            first_row = result["data"][0]
            value = list(first_row.values())[0] if first_row else None
            return {"success": True, "value": value}
        elif result["success"]:
            return {"success": True, "value": None}
        else:
            return {"success": False, "error": result.get("error"), "value": None}
