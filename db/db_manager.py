"""
Database Manager Module

Handles MSSQL database connections and stored procedure execution.
"""

import re
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

    def _validate_sql_type(self, sql_type: str) -> str:
        """
        Validate and normalize SQL Server data type.

        Args:
            sql_type: SQL Server type specification (e.g., "int", "varchar(50)")

        Returns:
            str: Validated type string

        Raises:
            ValueError: If type is invalid or contains suspicious characters
        """
        sql_type = sql_type.strip()

        # Valid SQL Server type patterns
        valid_patterns = [
            r"^int$",
            r"^bigint$",
            r"^smallint$",
            r"^tinyint$",
            r"^bit$",
            r"^decimal\(\d+,\s*\d+\)$",
            r"^numeric\(\d+,\s*\d+\)$",
            r"^float$",
            r"^real$",
            r"^money$",
            r"^smallmoney$",
            r"^char\(\d+\)$",
            r"^varchar\(\d+|max\)$",
            r"^nchar\(\d+\)$",
            r"^nvarchar\(\d+|max\)$",
            r"^text$",
            r"^ntext$",
            r"^datetime$",
            r"^datetime2$",
            r"^date$",
            r"^time$",
            r"^uniqueidentifier$",
            r"^binary\(\d+\)$",
            r"^varbinary\(\d+|max\)$",
        ]

        if any(
            re.match(pattern, sql_type, re.IGNORECASE) for pattern in valid_patterns
        ):
            return sql_type

        raise ValueError(
            f"Invalid or unsupported SQL type: '{sql_type}'. "
            "Must be a valid SQL Server data type (e.g., int, varchar(50), decimal(10,2))"
        )

    def _validate_parameter_name(self, param_name: str) -> str:
        """
        Validate SQL parameter name to prevent injection.

        Args:
            param_name: Parameter name to validate

        Returns:
            str: Validated parameter name with @ prefix

        Raises:
            ValueError: If parameter name is invalid
        """
        # Remove @ prefix if present
        if param_name.startswith("@"):
            param_name = param_name[1:]

        # Must be valid SQL identifier: alphanumeric and underscore, start with letter or underscore
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", param_name):
            raise ValueError(
                f"Invalid parameter name: '{param_name}'. "
                "Must contain only letters, numbers, and underscores, and start with a letter or underscore."
            )

        return f"@{param_name}"

    def _validate_procedure_name(self, procedure_name: str) -> str:
        """
        Validate stored procedure name to prevent SQL injection.

        Args:
            procedure_name: Procedure name to validate (optionally with schema prefix)

        Returns:
            str: Validated procedure name

        Raises:
            ValueError: If procedure name is invalid
        """
        procedure_name = procedure_name.strip()

        # Support schema.procedure format
        if "." in procedure_name:
            parts = procedure_name.split(".")
            if len(parts) != 2:
                raise ValueError(
                    f"Invalid procedure name: '{procedure_name}'. "
                    "Must be in format 'procedure' or 'schema.procedure'."
                )
            schema, proc = parts
            # Validate both parts
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema):
                raise ValueError(
                    f"Invalid schema name: '{schema}'. "
                    "Must contain only letters, numbers, and underscores, and start with a letter or underscore."
                )
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", proc):
                raise ValueError(
                    f"Invalid procedure name: '{proc}'. "
                    "Must contain only letters, numbers, and underscores, and start with a letter or underscore."
                )
        else:
            # Single identifier
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", procedure_name):
                raise ValueError(
                    f"Invalid procedure name: '{procedure_name}'. "
                    "Must contain only letters, numbers, and underscores, and start with a letter or underscore."
                )

        return procedure_name

    def _retrieve_output_params(
        self,
        cursor: pyodbc.Cursor,
        output_params: Dict[str, str],
        check_current: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieve output parameter values from cursor result sets.

        Iterates through all remaining result sets to find the one containing
        the expected output parameter columns. This handles cases where stored
        procedures return multiple result sets before the output parameters.

        Args:
            cursor: Database cursor after executing procedure
            output_params: Dictionary of expected output parameter names and types
            check_current: If True, check current result set before advancing.
                          If False, skip directly to nextset() iteration.
                          Set to False when current result set has been consumed.

        Returns:
            Dictionary of output parameter names (without @) and their values,
            or empty dict if output parameters not found
        """
        if not output_params:
            return {}

        # Normalize expected parameter names (remove @ prefix, lowercase)
        expected_params = set(
            param_name.lstrip("@").lower() for param_name in output_params.keys()
        )

        output_values = {}

        # Helper function to check and fetch from current result set
        def check_current_result_set():
            nonlocal output_values
            if not cursor.description:
                return False

            # Get column names (normalized)
            result_columns = [col[0].lower() for col in cursor.description]
            result_column_set = set(result_columns)

            # Check if this result set contains our expected output parameters
            if expected_params.issubset(result_column_set):
                # This is our output parameter result set
                output_row = cursor.fetchone()
                if output_row:
                    # Map original case column names to values
                    original_columns = [col[0] for col in cursor.description]
                    output_values = dict(zip(original_columns, output_row))
                    return True
            return False

        # Optionally check the CURRENT result set first (if not already consumed)
        if check_current:
            check_current_result_set()

        # Then iterate through remaining result sets
        while True:
            try:
                # Move to next result set
                if not cursor.nextset():
                    break

                # Check this result set
                check_current_result_set()

            except pyodbc.Error:
                # No more result sets or error moving to next
                break

        return output_values

    def _build_procedure_sql(
        self,
        procedure_name: str,
        parameters: Dict[str, Any],
        output_params: Optional[Dict[str, str]] = None,
    ) -> tuple[str, list]:
        """
        Build SQL statement for stored procedure execution with output parameters.

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of input parameter names and values
            output_params: Dictionary of output parameter names and SQL types

        Returns:
            Tuple of (sql_statement, input_values_list)
        """
        output_params = output_params or {}
        parameters = parameters or {}

        # Validate procedure name
        validated_procedure_name = self._validate_procedure_name(procedure_name)

        # Validate output parameter names and types
        validated_output_params = {}
        for param_name, sql_type in output_params.items():
            validated_name = self._validate_parameter_name(param_name)
            validated_type = self._validate_sql_type(sql_type)
            validated_output_params[validated_name] = validated_type

        # Build DECLARE statements for output parameters
        declare_statements = []
        for param_name, sql_type in validated_output_params.items():
            declare_statements.append(f"DECLARE {param_name} {sql_type};")

        # Build parameter list for EXEC statement
        exec_params = []
        input_values = []

        # Add input parameters with positional placeholders
        for param_name, param_value in parameters.items():
            validated_name = self._validate_parameter_name(param_name)
            exec_params.append(f"{validated_name} = ?")
            input_values.append(param_value)

        # Add output parameters
        for param_name in validated_output_params.keys():
            exec_params.append(f"{param_name} = {param_name} OUTPUT")

        # Build EXEC statement
        exec_statement = f"EXEC {validated_procedure_name}"
        if exec_params:
            exec_statement += " " + ", ".join(exec_params) + ";"
        else:
            exec_statement += ";"

        # Build SELECT statement to retrieve output values
        select_statement = ""
        if validated_output_params:
            select_parts = [
                f"{param_name} AS {param_name[1:]}"  # Remove @ prefix for column alias
                for param_name in validated_output_params.keys()
            ]
            select_statement = "\nSELECT " + ", ".join(select_parts) + ";"

        # Combine all parts
        sql_parts = (
            declare_statements
            + [exec_statement]
            + ([select_statement] if select_statement else [])
        )
        full_sql = "\n".join(sql_parts)

        return full_sql, input_values

    def execute_stored_procedure(
        self,
        procedure_name: str,
        parameters: Dict[str, Any] = None,
        output_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure (for INSERT, UPDATE, DELETE operations).

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of input parameter names and values
            output_params: Dictionary of output parameter names and SQL types
                          (e.g., {"user_id": "int", "status": "varchar(20)"})

        Returns:
            Dict with keys:
                - success (bool): Whether execution was successful
                - affected_rows (int): Number of rows affected
                - output_values (Dict[str, Any]): Output parameter values (if any)
                - error (str): Error message if failed
        """
        parameters = parameters or {}
        output_params = output_params or {}

        try:
            with self.get_cursor() as cursor:
                # Build SQL with output parameters
                sql, input_values = self._build_procedure_sql(
                    procedure_name, parameters, output_params
                )

                logger.debug(f"Executing procedure: {procedure_name}")

                cursor.execute(sql, input_values)
                affected_rows = cursor.rowcount

                # Retrieve output parameter values if any
                output_values = {}
                if output_params:
                    output_values = self._retrieve_output_params(cursor, output_params)
                    if output_values:
                        logger.debug(
                            f"Output parameters retrieved for {procedure_name}"
                        )

                # Commit transaction
                self._connection.commit()

                logger.info(
                    f"Stored procedure executed: {procedure_name}, affected rows: {affected_rows}"
                )

                return {
                    "success": True,
                    "affected_rows": affected_rows,
                    "output_values": output_values,
                }

        except pyodbc.Error as e:
            logger.error(f"Database error in {procedure_name}: {str(e)}", exc_info=True)
            try:
                self._connection.rollback()
            except Exception as rollback_error:
                logger.error(
                    f"Rollback failed for {procedure_name}: {str(rollback_error)}"
                )
            return {
                "success": False,
                "error": str(e),
                "affected_rows": 0,
                "output_values": {},
            }
        except Exception as e:
            logger.error(
                f"Unexpected error in {procedure_name}: {str(e)}", exc_info=True
            )
            try:
                self._connection.rollback()
            except Exception as rollback_error:
                logger.error(
                    f"Rollback failed for {procedure_name}: {str(rollback_error)}"
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
        parameters: Dict[str, Any] = None,
        output_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure that returns data (SELECT operations).

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of input parameter names and values
            output_params: Dictionary of output parameter names and SQL types
                          (e.g., {"user_id": "int", "status": "varchar(20)"})

        Returns:
            Dict with keys:
                - success (bool): Whether execution was successful
                - data (List[Dict]): List of rows as dictionaries
                - output_values (Dict[str, Any]): Output parameter values (if any)
                - error (str): Error message if failed
        """
        parameters = parameters or {}
        output_params = output_params or {}

        try:
            with self.get_cursor() as cursor:
                # Build SQL with output parameters
                sql, input_values = self._build_procedure_sql(
                    procedure_name, parameters, output_params
                )

                logger.debug(f"Executing query procedure: {procedure_name}")

                cursor.execute(sql, input_values)

                # Fetch all results from the main result set
                columns = (
                    [column[0] for column in cursor.description]
                    if cursor.description
                    else []
                )
                results = []

                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))

                # Retrieve output parameter values if any
                output_values = {}
                if output_params:
                    # Current result set has been consumed, skip directly to next
                    output_values = self._retrieve_output_params(
                        cursor, output_params, check_current=False
                    )
                    if output_values:
                        logger.debug(
                            f"Output parameters retrieved for {procedure_name}"
                        )

                logger.info(
                    f"Query procedure executed: {procedure_name}, returned {len(results)} rows"
                )

                return {
                    "success": True,
                    "data": results,
                    "output_values": output_values,
                }

        except pyodbc.Error as e:
            logger.error(f"Database error in {procedure_name}: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "output_values": {},
            }
        except Exception as e:
            logger.error(
                f"Unexpected error in {procedure_name}: {str(e)}", exc_info=True
            )
            return {
                "success": False,
                "error": str(e),
                "data": [],
                "output_values": {},
            }

    def execute_scalar_procedure(
        self,
        procedure_name: str,
        parameters: Dict[str, Any] = None,
        output_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure that returns a single value.

        Args:
            procedure_name: Name of the stored procedure
            parameters: Dictionary of input parameter names and values
            output_params: Dictionary of output parameter names and SQL types
                          (e.g., {"user_id": "int", "status": "varchar(20)"})

        Returns:
            Dict with keys:
                - success (bool): Whether execution was successful
                - value (Any): The scalar value returned
                - output_values (Dict[str, Any]): Output parameter values (if any)
                - error (str): Error message if failed
        """
        result = self.execute_query_procedure(procedure_name, parameters, output_params)

        if result["success"] and result["data"]:
            # Get first column of first row
            first_row = result["data"][0]
            value = list(first_row.values())[0] if first_row else None
            return {
                "success": True,
                "value": value,
                "output_values": result.get("output_values", {}),
            }
        elif result["success"]:
            return {
                "success": True,
                "value": None,
                "output_values": result.get("output_values", {}),
            }
        else:
            return {
                "success": False,
                "error": result.get("error"),
                "value": None,
                "output_values": {},
            }
