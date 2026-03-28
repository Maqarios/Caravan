"""
Database Client Module

Client for interacting with the database service API.
Used by bot and web services to execute stored procedures.
"""

import hashlib
import os
from typing import Any, Dict, Optional, Union

import httpx

from .logger import get_logger

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
                "/api/v1/execute",
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
                "/api/v1/query",
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

    def add_user(
        self,
        username: str,
        password: str,
        discord_id: Union[int, str],
        sec_password: Optional[str] = None,
        full_name: Optional[str] = None,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        sex: Optional[str] = None,
        birthday: Optional[str] = None,
        province: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        reg_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Register a new user account via usp_AddUser stored procedure.

        This method handles user registration with automatic MD5 password hashing,
        Discord ID integration, and output parameter retrieval for the generated JID.

        Args:
            username: User account username (max 25 chars) - MANDATORY
            password: User account password (will be MD5 hashed) - MANDATORY
            discord_id: Discord user ID for account linking - MANDATORY
            sec_password: Secondary password (defaults to same as password if not provided)
            full_name: User's full name (max 30 chars)
            question: Security question (max 50 chars)
            answer: Security answer (max 100 chars)
            sex: User's sex/gender (2 chars)
            birthday: User's birthday (datetime string or None)
            province: User's province (max 50 chars)
            address: User's address (max 100 chars)
            phone: User's phone number (max 20 chars)
            mobile: User's mobile number (max 20 chars)
            email: User's email (defaults to {discord_id}@discord.user)
            reg_ip: Registration IP address (max 15 chars)

        Returns:
            Dictionary with:
                - success (bool): Whether registration was successful
                - jid (int): Generated user JID (user ID) if successful
                - affected_rows (int): Number of rows affected
                - error (str): Error message if failed

        Example:
            >>> client = DatabaseClient()
            >>> result = client.add_user(
            ...     username="player123",
            ...     password="mypassword",
            ...     discord_id=123456789012345678,
            ...     full_name="John Doe",
            ...     reg_ip="192.168.1.1"
            ... )
            >>> if result["success"]:
            ...     print(f"User created with JID: {result['jid']}")
        """
        try:
            # Validate mandatory parameters
            if not username or not password or not discord_id:
                error_msg = (
                    "username, password, and discord_id are mandatory parameters"
                )
                logger.error(f"User registration failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "jid": None,
                    "affected_rows": 0,
                }

            # Convert discord_id to string (supports int or str input)
            discord_id_str = str(discord_id)

            # MD5 hash the password
            hashed_password = hashlib.md5(password.encode()).hexdigest()

            # Use same password for secondary if not provided
            if sec_password:
                hashed_sec_password = hashlib.md5(sec_password.encode()).hexdigest()
            else:
                hashed_sec_password = hashed_password

            # Auto-generate email from discord_id if not provided
            if not email:
                email = f"{discord_id_str}@discord.user"

            # Build parameters dictionary matching stored procedure parameter names
            parameters = {
                "StrUserID": username,
                "Password": hashed_password,
                "SecPassword": hashed_sec_password,
                "FullName": full_name,
                "Question": question,
                "Answer": answer,
                "Sex": sex,
                "BirthDay": birthday,
                "Province": province,
                "Address": address,
                "Phone": phone,
                "Mobile": mobile,
                "Email": email,
                "cid": discord_id_str,  # Certificate ID
                "RegIP": reg_ip,
            }

            # Define output parameters
            output_params = {"JID": "int"}

            logger.info(
                f"Registering new user: {username} (Discord ID: {discord_id_str})"
            )

            # Execute stored procedure using the new smart endpoint
            response = self._make_request(
                "POST",
                "/api/v1/execute",
                json_data={
                    "database": "SRO_VT_ACCOUNT",
                    "procedure_name": "usp_AddUser",
                    "parameters": parameters,
                    "output_params": output_params,
                },
            )

            # Extract JID from output_values
            if response.get("success"):
                jid = response.get("output_values", {}).get("JID")
                logger.info(f"User registered successfully: {username} with JID: {jid}")
                return {
                    "success": True,
                    "jid": jid,
                    "affected_rows": response.get("affected_rows", 0),
                }
            else:
                error_msg = response.get("error", "Unknown error")
                logger.error(f"User registration failed for {username}: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "jid": None,
                    "affected_rows": 0,
                }

        except httpx.HTTPStatusError as e:
            error_msg = f"Database service error: {e.response.status_code}"
            logger.error(f"HTTP error during user registration: {e.response.text}")
            return {
                "success": False,
                "error": error_msg,
                "jid": None,
                "affected_rows": 0,
            }
        except Exception as e:
            logger.error(f"Error registering user: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "jid": None,
                "affected_rows": 0,
            }

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

            url = f"{self.base_url}/api/v1/execute"
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

            url = f"{self.base_url}/api/v1/query"
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

    async def async_add_user(
        self,
        username: str,
        password: str,
        discord_id: Union[int, str],
        sec_password: Optional[str] = None,
        full_name: Optional[str] = None,
        question: Optional[str] = None,
        answer: Optional[str] = None,
        sex: Optional[str] = None,
        birthday: Optional[str] = None,
        province: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        mobile: Optional[str] = None,
        email: Optional[str] = None,
        reg_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Async version - Register a new user account via usp_AddUser stored procedure.

        This method handles user registration with automatic MD5 password hashing,
        Discord ID integration, and output parameter retrieval for the generated JID.

        Args:
            username: User account username (max 25 chars) - MANDATORY
            password: User account password (will be MD5 hashed) - MANDATORY
            discord_id: Discord user ID for account linking - MANDATORY
            sec_password: Secondary password (defaults to same as password if not provided)
            full_name: User's full name (max 30 chars)
            question: Security question (max 50 chars)
            answer: Security answer (max 100 chars)
            sex: User's sex/gender (2 chars)
            birthday: User's birthday (datetime string or None)
            province: User's province (max 50 chars)
            address: User's address (max 100 chars)
            phone: User's phone number (max 20 chars)
            mobile: User's mobile number (max 20 chars)
            email: User's email (defaults to {discord_id}@discord.user)
            reg_ip: Registration IP address (max 15 chars)

        Returns:
            Dictionary with:
                - success (bool): Whether registration was successful
                - jid (int): Generated user JID (user ID) if successful
                - affected_rows (int): Number of rows affected
                - error (str): Error message if failed

        Example:
            >>> client = DatabaseClient()
            >>> result = await client.async_add_user(
            ...     username="player123",
            ...     password="mypassword",
            ...     discord_id=123456789012345678,
            ...     full_name="John Doe",
            ...     reg_ip="192.168.1.1"
            ... )
            >>> if result["success"]:
            ...     print(f"User created with JID: {result['jid']}")
        """
        try:
            # Validate mandatory parameters
            if not username or not password or not discord_id:
                error_msg = (
                    "username, password, and discord_id are mandatory parameters"
                )
                logger.error(f"User registration failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "jid": None,
                    "affected_rows": 0,
                }

            # Convert discord_id to string (supports int or str input)
            discord_id_str = str(discord_id)

            # MD5 hash the password
            hashed_password = hashlib.md5(password.encode()).hexdigest()

            # Use same password for secondary if not provided
            if sec_password:
                hashed_sec_password = hashlib.md5(sec_password.encode()).hexdigest()
            else:
                hashed_sec_password = hashed_password

            # Auto-generate email from discord_id if not provided
            if not email:
                email = f"{discord_id_str}@discord.user"

            # Build parameters dictionary matching stored procedure parameter names
            parameters = {
                "StrUserID": username,
                "Password": hashed_password,
                "SecPassword": hashed_sec_password,
                "FullName": full_name,
                "Question": question,
                "Answer": answer,
                "Sex": sex,
                "BirthDay": birthday,
                "Province": province,
                "Address": address,
                "Phone": phone,
                "Mobile": mobile,
                "Email": email,
                "cid": discord_id_str,  # Certificate ID
                "RegIP": reg_ip,
            }

            # Define output parameters
            output_params = {"JID": "int"}

            logger.info(
                f"Registering new user (async): {username} (Discord ID: {discord_id_str})"
            )

            # Execute stored procedure using the new smart endpoint
            url = f"{self.base_url}/api/v1/execute"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json={
                        "database": "SRO_VT_ACCOUNT",
                        "procedure_name": "usp_AddUser",
                        "parameters": parameters,
                        "output_params": output_params,
                    },
                )
                response.raise_for_status()
                result = response.json()

            # Extract JID from output_values
            if result.get("success"):
                jid = result.get("output_values", {}).get("JID")
                logger.info(
                    f"User registered successfully (async): {username} with JID: {jid}"
                )
                return {
                    "success": True,
                    "jid": jid,
                    "affected_rows": result.get("affected_rows", 0),
                }
            else:
                error_msg = result.get("error", "Unknown error")
                logger.error(
                    f"User registration failed (async) for {username}: {error_msg}"
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "jid": None,
                    "affected_rows": 0,
                }

        except httpx.HTTPStatusError as e:
            error_msg = f"Database service error: {e.response.status_code}"
            logger.error(
                f"HTTP error during user registration (async): {e.response.text}"
            )
            return {
                "success": False,
                "error": error_msg,
                "jid": None,
                "affected_rows": 0,
            }
        except Exception as e:
            logger.error(f"Error registering user (async): {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "jid": None,
                "affected_rows": 0,
            }
