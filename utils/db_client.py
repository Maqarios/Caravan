"""
Database Client Module

Client for interacting with the database service API.
Used by bot and web services to execute stored procedures.
"""

import os
from typing import Any, Dict, Optional

import httpx

from utils import get_logger

logger = get_logger("db")


class DatabaseClient:
    """
    Client for communicating with the database service.

    This client provides a simple interface for bot and web services
    to execute stored procedures via the database service API.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0):
        """
        Initialize database client.

        Args:
            base_url: Base URL of the database service (default: from env var)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url or os.getenv(
            "DB_SERVICE_URL", "http://db:8080"  # Default for Docker Compose
        )
        self.timeout = timeout

        logger.info(f"DatabaseClient initialized with base URL: {self.base_url}")

    def _make_request(
        self, method: str, endpoint: str, json_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to database service.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            json_data: JSON data to send

        Returns:
            Response data as dictionary

        Raises:
            Exception: If request fails
        """
        url = f"{self.base_url}{endpoint}"

        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method == "GET":
                    response = client.get(url)
                elif method == "POST":
                    response = client.post(url, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise Exception(f"Database service error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}")
            raise Exception(f"Failed to connect to database service: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            raise

    def health_check(self) -> Dict[str, Any]:
        """
        Check database service health.

        Returns:
            Health status dictionary
        """
        try:
            return self._make_request("GET", "/health")
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {"status": "unhealthy", "database_connected": False, "error": str(e)}

    def is_healthy(self) -> bool:
        """
        Check if database service is healthy.

        Returns:
            True if at least one database is connected, False otherwise
        """
        health = self.health_check()
        return (
            health.get("status") == "healthy" and health.get("connected_count", 0) > 0
        )

    def execute_procedure(
        self,
        database: str,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure (INSERT, UPDATE, DELETE).

        Args:
            database: Database name to use
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dictionary with:
                - success (bool): Whether execution was successful
                - affected_rows (int): Number of rows affected
                - error (str): Error message if failed
        """
        try:
            logger.info(f"Executing procedure in '{database}': {procedure_name}")

            response = self._make_request(
                "POST",
                "/execute",
                json_data={
                    "database": database,
                    "procedure_name": procedure_name,
                    "parameters": parameters or {},
                },
            )

            if response.get("success"):
                logger.info(
                    f"Procedure executed successfully in '{database}': {procedure_name}"
                )
            else:
                logger.error(
                    f"Procedure execution failed in '{database}': {response.get('error')}"
                )

            return response

        except Exception as e:
            logger.error(f"Error executing procedure: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e), "affected_rows": 0}

    def execute_query(
        self,
        database: str,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a stored procedure that returns data (SELECT).

        Args:
            database: Database name to use
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dictionary with:
                - success (bool): Whether execution was successful
                - data (List[Dict]): List of rows as dictionaries
                - error (str): Error message if failed
        """
        try:
            logger.info(f"Executing query procedure in '{database}': {procedure_name}")

            response = self._make_request(
                "POST",
                "/execute-query",
                json_data={
                    "database": database,
                    "procedure_name": procedure_name,
                    "parameters": parameters or {},
                },
            )

            if response.get("success"):
                row_count = len(response.get("data", []))
                logger.info(
                    f"Query executed successfully in '{database}': {procedure_name}, {row_count} rows returned"
                )
            else:
                logger.error(
                    f"Query execution failed in '{database}': {response.get('error')}"
                )

            return response

        except Exception as e:
            logger.error(f"Error executing query: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e), "data": []}

    async def async_execute_procedure(
        self,
        database: str,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Async version - execute a stored procedure (INSERT, UPDATE, DELETE).

        Args:
            database: Database name to use
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dictionary with execution results
        """
        try:
            logger.info(
                f"Executing procedure (async) in '{database}': {procedure_name}"
            )

            url = f"{self.base_url}/execute"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "database": database,
                        "procedure_name": procedure_name,
                        "parameters": parameters or {},
                    },
                )
                response.raise_for_status()
                result = response.json()

            if result.get("success"):
                logger.info(
                    f"Procedure executed successfully (async) in '{database}': {procedure_name}"
                )
            else:
                logger.error(
                    f"Procedure execution failed (async) in '{database}': {result.get('error')}"
                )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            return {
                "success": False,
                "error": f"Database service error: {e.response.status_code}",
                "affected_rows": 0,
            }
        except Exception as e:
            logger.error(f"Error executing procedure (async): {str(e)}", exc_info=True)
            return {"success": False, "error": str(e), "affected_rows": 0}

    async def async_execute_query(
        self,
        database: str,
        procedure_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Async version - execute a stored procedure that returns data (SELECT).

        Args:
            database: Database name to use
            procedure_name: Name of the stored procedure
            parameters: Dictionary of parameter names and values

        Returns:
            Dictionary with query results
        """
        try:
            logger.info(
                f"Executing query procedure (async) in '{database}': {procedure_name}"
            )

            url = f"{self.base_url}/execute-query"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "database": database,
                        "procedure_name": procedure_name,
                        "parameters": parameters or {},
                    },
                )
                response.raise_for_status()
                result = response.json()

            if result.get("success"):
                row_count = len(result.get("data", []))
                logger.info(
                    f"Query executed successfully (async) in '{database}': {procedure_name}, {row_count} rows returned"
                )
            else:
                logger.error(
                    f"Query execution failed (async) in '{database}': {result.get('error')}"
                )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            return {
                "success": False,
                "error": f"Database service error: {e.response.status_code}",
                "data": [],
            }
        except Exception as e:
            logger.error(f"Error executing query (async): {str(e)}", exc_info=True)
            return {"success": False, "error": str(e), "data": []}
