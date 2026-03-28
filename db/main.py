"""
Caravan Database Service - Main Entry Point

A FastAPI-based microservice for MSSQL database operations using stored procedures.
Shared by both bot and web services.
"""

import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

from db_pool import DatabasePoolManager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from utils import get_logger, set_log_level

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger("db")
set_log_level("db", os.getenv("DB_LOG_LEVEL", 20))

# Global database pool manager instance
db_pool: Optional[DatabasePoolManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    global db_pool

    # Startup
    logger.info("Starting database service...")

    # Validate environment variables
    required_env_vars = ["MSSQL_SERVER", "MSSQL_USERNAME", "MSSQL_PASSWORD"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Validate port
    try:
        port = int(os.getenv("MSSQL_PORT", "1433"))
        if port < 1 or port > 65535:
            raise ValueError(f"Invalid port number: {port}")
    except ValueError as e:
        logger.error(f"Invalid MSSQL_PORT: {str(e)}")
        raise ValueError(f"MSSQL_PORT must be a valid port number (1-65535): {str(e)}")

    # Get database names from environment (comma-separated)
    databases_str = os.getenv("MSSQL_DATABASES", os.getenv("MSSQL_DATABASE", ""))
    databases = [db.strip() for db in databases_str.split(",") if db.strip()]

    if not databases:
        logger.error("No databases configured! Set MSSQL_DATABASES or MSSQL_DATABASE")
        raise ValueError("No databases configured")

    logger.info(
        f"Configuring connections for {len(databases)} database(s): {', '.join(databases)}"
    )

    # Get pool size configuration
    try:
        pool_size = int(os.getenv("DB_POOL_SIZE_PER_DB", "5"))
        if pool_size < 1 or pool_size > 50:
            raise ValueError(f"Pool size must be between 1 and 50, got {pool_size}")
    except ValueError as e:
        logger.error(f"Invalid DB_POOL_SIZE_PER_DB: {str(e)}")
        pool_size = 5  # Use default

    db_pool = DatabasePoolManager(
        server=os.getenv("MSSQL_SERVER"),
        username=os.getenv("MSSQL_USERNAME"),
        password=os.getenv("MSSQL_PASSWORD"),
        databases=databases,
        port=port,
        pool_size_per_db=pool_size,
    )

    results = db_pool.connect_all()

    # Log connection results
    connected = [db for db, success in results.items() if success]
    failed = [db for db, success in results.items() if not success]

    if connected:
        logger.info(f"Successfully connected to: {', '.join(connected)}")
    if failed:
        logger.warning(f"Failed to connect to: {', '.join(failed)}")

    if not connected:
        logger.error("Failed to establish any database connections")

    yield

    # Shutdown
    logger.info("Shutting down database service...")
    if db_pool:
        db_pool.disconnect_all()
    logger.info("Database service stopped")


# Initialize FastAPI app
app = FastAPI(
    title="Caravan Database Service",
    description="MSSQL database operations via stored procedures with connection pooling",
    version="2.0.0",
    lifespan=lifespan,
)


# Middleware for request correlation IDs and logging
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Add correlation ID to requests for distributed tracing.

    Checks for X-Request-ID header, generates one if missing.
    Logs request/response information.
    """
    # Get or generate correlation ID
    correlation_id = request.headers.get("X-Request-ID")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    # Store in request state for access in endpoints
    request.state.correlation_id = correlation_id

    # Log request
    start_time = time.time()
    logger.info(
        f"[{correlation_id}] {request.method} {request.url.path} - Request started"
    )

    # Process request
    try:
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Log response
        logger.info(
            f"[{correlation_id}] {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {duration:.3f}s"
        )

        # Add correlation ID to response headers
        response.headers["X-Request-ID"] = correlation_id
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        return response

    except Exception as e:
        # Log error
        duration = time.time() - start_time
        logger.error(
            f"[{correlation_id}] {request.method} {request.url.path} - "
            f"Error: {str(e)} - Duration: {duration:.3f}s",
            exc_info=True,
        )
        raise


# Request/Response models
class StoredProcedureRequest(BaseModel):
    """Request model for executing a stored procedure"""

    database: str = Field(..., description="Database name to execute procedure in")
    procedure_name: str = Field(..., description="Name of the stored procedure")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Input parameters for the procedure"
    )
    output_params: Dict[str, str] = Field(
        default_factory=dict,
        description="Output parameters with their SQL types (e.g., {'user_id': 'int'})",
    )

    @field_validator("database")
    @classmethod
    def validate_database(cls, v: str) -> str:
        """Validate database name format"""
        if not v or not v.strip():
            raise ValueError("Database name cannot be empty")
        # Basic SQL identifier validation
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
            raise ValueError(
                "Database name must start with letter/underscore and contain only alphanumeric characters and underscores"
            )
        return v.strip()

    @field_validator("procedure_name")
    @classmethod
    def validate_procedure_name(cls, v: str) -> str:
        """Validate procedure name format (supports schema.procedure)"""
        if not v or not v.strip():
            raise ValueError("Procedure name cannot be empty")

        v = v.strip()

        # Support schema.procedure format
        if "." in v:
            parts = v.split(".")
            if len(parts) != 2:
                raise ValueError(
                    "Procedure name must be 'procedure' or 'schema.procedure' format"
                )
            schema, proc = parts
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema):
                raise ValueError(f"Invalid schema name: {schema}")
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", proc):
                raise ValueError(f"Invalid procedure name: {proc}")
        else:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", v):
                raise ValueError(
                    "Procedure name must start with letter/underscore and contain only alphanumeric characters and underscore"
                )

        return v

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters dictionary size"""
        if len(v) > 100:  # Reasonable limit
            raise ValueError("Too many parameters (max 100)")
        return v


class ExecuteResponse(BaseModel):
    """Response for procedures that don't return data (INSERT, UPDATE, DELETE)"""

    success: bool = Field(..., description="Whether execution was successful")
    database: str = Field(..., description="Database name")
    procedure_name: str = Field(..., description="Procedure name")
    affected_rows: int = Field(..., description="Number of rows affected")
    output_values: Dict[str, Any] = Field(
        default_factory=dict, description="Output parameter values"
    )


class QueryResponse(BaseModel):
    """Response for procedures that return data (SELECT)"""

    success: bool = Field(..., description="Whether execution was successful")
    database: str = Field(..., description="Database name")
    procedure_name: str = Field(..., description="Procedure name")
    data: List[Dict[str, Any]] = Field(..., description="Query result rows")
    row_count: int = Field(..., description="Number of rows returned")
    output_values: Dict[str, Any] = Field(
        default_factory=dict, description="Output parameter values"
    )


class ErrorResponse(BaseModel):
    """Error response model"""

    success: bool = Field(default=False, description="Always false for errors")
    error_code: str = Field(..., description="Error code identifier")
    message: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    database: Optional[str] = Field(None, description="Database name if applicable")
    procedure_name: Optional[str] = Field(
        None, description="Procedure name if applicable"
    )


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    databases: Dict[str, bool]
    connected_count: int
    total_count: int
    pool_stats: Optional[Dict[str, Dict]] = None


# Dependency to get database pool manager
def get_db_pool() -> DatabasePoolManager:
    """Get the global database pool manager instance"""
    if db_pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service not initialized",
        )
    return db_pool


# API Endpoints
@app.get("/", response_model=Dict[str, Any])
async def root():
    """Root endpoint with service information"""
    if db_pool:
        connected_dbs = db_pool.get_connected_databases()
        health_stats = db_pool.get_health_stats()
        return {
            "service": "Caravan Database Service",
            "version": "2.0.0",
            "status": "running",
            "databases": connected_dbs,
            "database_count": len(connected_dbs),
            "features": [
                "Connection pooling",
                "OUTPUT parameters",
                "Smart endpoint (auto-detect query vs execute)",
                "Proper HTTP status codes",
            ],
            "health": health_stats,
        }
    return {
        "service": "Caravan Database Service",
        "version": "2.0.0",
        "status": "running",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(pool: DatabasePoolManager = Depends(get_db_pool)):
    """
    Health check endpoint with pool statistics.

    Tests actual database connectivity by executing a simple query.
    """
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service not initialized",
        )

    db_status = pool.get_all_status()
    pool_stats = pool.get_health_stats()
    connected_count = sum(1 for connected in db_status.values() if connected)

    # Test actual connectivity by trying to get a connection from each pool
    for db_name in pool.databases:
        if db_name in pool._pools:
            try:
                with pool.get_connection(db_name, timeout=5.0) as manager:
                    # Execute a simple test query
                    test_result = manager.execute_query_procedure(
                        procedure_name="sp_who",  # Built-in SQL Server procedure
                        parameters={},
                        output_params={},
                    )
                    if not test_result.get("success"):
                        logger.warning(f"Health check query failed for '{db_name}'")
                        db_status[db_name] = False
            except Exception as e:
                logger.warning(f"Health check failed for '{db_name}': {str(e)}")
                db_status[db_name] = False

    # Recalculate connected count after tests
    connected_count = sum(1 for connected in db_status.values() if connected)

    return HealthResponse(
        status="healthy" if connected_count > 0 else "unhealthy",
        databases=db_status,
        connected_count=connected_count,
        total_count=len(db_status),
        pool_stats=pool_stats,
    )


@app.post(
    "/api/v1/query",
    response_model=QueryResponse,
    responses={
        200: {"description": "Query executed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def query_procedure(
    request: StoredProcedureRequest, pool: DatabasePoolManager = Depends(get_db_pool)
):
    """
    Execute a stored procedure that returns data (SELECT operations).

    Use this endpoint for procedures that return result sets.
    Supports OUTPUT parameters through the output_params field.

    Args:
        request: StoredProcedureRequest with database, procedure, and parameters
        pool: DatabasePoolManager instance (injected)

    Returns:
        QueryResponse with result set and output parameter values

    Raises:
        HTTPException: With appropriate status code for different error types
    """
    try:
        # Validate database exists in pool
        if request.database not in pool.databases:
            logger.error(f"Database '{request.database}' not configured")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "INVALID_DATABASE",
                    "message": f"Database '{request.database}' is not configured",
                    "details": f"Available databases: {', '.join(pool.databases)}",
                    "database": request.database,
                },
            )

        # Get database manager
        db_manager = pool.get_manager(request.database)

        if db_manager is None:
            logger.error(f"Database '{request.database}' not found or not connected")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "success": False,
                    "error_code": "DATABASE_UNAVAILABLE",
                    "message": f"Database '{request.database}' is not available",
                    "details": "Database connection could not be established",
                    "database": request.database,
                },
            )

        logger.info(
            f"Executing query procedure '{request.procedure_name}' in '{request.database}'"
        )

        # Execute as query procedure
        result = db_manager.execute_query_procedure(
            procedure_name=request.procedure_name,
            parameters=request.parameters,
            output_params=request.output_params,
        )
        logger.debug(f"Executing Query Procedure Result: {result}")

        if not result["success"]:
            # Execution failed
            error_msg = result.get("error", "Unknown error")
            logger.error(
                f"Query procedure '{request.procedure_name}' in '{request.database}' failed: {error_msg}"
            )

            # Determine if it's a validation error or execution error
            if "Invalid" in error_msg or "validation" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "success": False,
                        "error_code": "VALIDATION_ERROR",
                        "message": "Procedure execution validation failed",
                        "details": error_msg,
                        "database": request.database,
                        "procedure_name": request.procedure_name,
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "success": False,
                        "error_code": "EXECUTION_ERROR",
                        "message": "Query procedure execution failed",
                        "details": error_msg,
                        "database": request.database,
                        "procedure_name": request.procedure_name,
                    },
                )

        # Return query response
        data = result.get("data", [])
        output_values = result.get("output_values", {})

        logger.info(
            f"Query procedure '{request.procedure_name}' in '{request.database}' "
            f"returned {len(data)} rows"
        )
        return QueryResponse(
            success=True,
            database=request.database,
            procedure_name=request.procedure_name,
            data=data,
            row_count=len(data),
            output_values=output_values,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error executing query procedure '{request.procedure_name}' "
            f"in '{request.database}': {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": str(e),
                "database": request.database,
                "procedure_name": request.procedure_name,
            },
        )


@app.post(
    "/api/v1/execute",
    response_model=ExecuteResponse,
    responses={
        200: {"description": "Procedure executed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid request"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        503: {"model": ErrorResponse, "description": "Database unavailable"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def execute_procedure(
    request: StoredProcedureRequest, pool: DatabasePoolManager = Depends(get_db_pool)
):
    """
    Execute a stored procedure that modifies data (INSERT/UPDATE/DELETE operations).

    Use this endpoint for procedures that modify data and return affected row counts.
    Supports OUTPUT parameters through the output_params field.

    Args:
        request: StoredProcedureRequest with database, procedure, and parameters
        pool: DatabasePoolManager instance (injected)

    Returns:
        ExecuteResponse with affected rows and output parameter values

    Raises:
        HTTPException: With appropriate status code for different error types
    """
    try:
        # Validate database exists in pool
        if request.database not in pool.databases:
            logger.error(f"Database '{request.database}' not configured")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error_code": "INVALID_DATABASE",
                    "message": f"Database '{request.database}' is not configured",
                    "details": f"Available databases: {', '.join(pool.databases)}",
                    "database": request.database,
                },
            )

        # Get database manager
        db_manager = pool.get_manager(request.database)

        if db_manager is None:
            logger.error(f"Database '{request.database}' not found or not connected")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "success": False,
                    "error_code": "DATABASE_UNAVAILABLE",
                    "message": f"Database '{request.database}' is not available",
                    "details": "Database connection could not be established",
                    "database": request.database,
                },
            )

        logger.info(
            f"Executing procedure '{request.procedure_name}' in '{request.database}'"
        )

        # Execute as stored procedure (non-query)
        result = db_manager.execute_stored_procedure(
            procedure_name=request.procedure_name,
            parameters=request.parameters,
            output_params=request.output_params,
        )
        logger.debug(f"Executing Stored Procedure Result: {result}")

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            logger.error(
                f"Procedure '{request.procedure_name}' in '{request.database}' failed: {error_msg}"
            )

            # Determine if it's a validation error or execution error
            if "Invalid" in error_msg or "validation" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "success": False,
                        "error_code": "VALIDATION_ERROR",
                        "message": "Procedure execution validation failed",
                        "details": error_msg,
                        "database": request.database,
                        "procedure_name": request.procedure_name,
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "success": False,
                        "error_code": "EXECUTION_ERROR",
                        "message": "Procedure execution failed",
                        "details": error_msg,
                        "database": request.database,
                        "procedure_name": request.procedure_name,
                    },
                )

        affected_rows = result.get("affected_rows", 0)
        output_values = result.get("output_values", {})

        logger.info(
            f"Procedure '{request.procedure_name}' in '{request.database}' "
            f"affected {affected_rows} rows"
        )
        return ExecuteResponse(
            success=True,
            database=request.database,
            procedure_name=request.procedure_name,
            affected_rows=affected_rows,
            output_values=output_values,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error executing procedure '{request.procedure_name}' "
            f"in '{request.database}': {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error_code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": str(e),
                "database": request.database,
                "procedure_name": request.procedure_name,
            },
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("DB_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("DB_SERVICE_PORT", "8080"))

    logger.info(f"Starting database service on {host}:{port}")

    uvicorn.run("main:app", host=host, port=port, log_level="info", reload=False)
