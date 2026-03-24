"""
Caravan Database Service - Main Entry Point

A FastAPI-based microservice for MSSQL database operations using stored procedures.
Shared by both bot and web services.
"""

import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from db_pool import DatabasePoolManager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

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

    # Get database names from environment (comma-separated)
    databases_str = os.getenv("MSSQL_DATABASES", os.getenv("MSSQL_DATABASE", ""))
    databases = [db.strip() for db in databases_str.split(",") if db.strip()]

    if not databases:
        logger.error("No databases configured! Set MSSQL_DATABASES or MSSQL_DATABASE")
        raise ValueError("No databases configured")

    logger.info(
        f"Configuring connections for {len(databases)} database(s): {', '.join(databases)}"
    )

    db_pool = DatabasePoolManager(
        server=os.getenv("MSSQL_SERVER"),
        username=os.getenv("MSSQL_USERNAME"),
        password=os.getenv("MSSQL_PASSWORD"),
        databases=databases,
        port=int(os.getenv("MSSQL_PORT", "1433")),
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
    description="MSSQL database operations via stored procedures",
    version="1.0.0",
    lifespan=lifespan,
)


# Request/Response models
class StoredProcedureRequest(BaseModel):
    """Request model for executing a stored procedure"""

    database: str
    procedure_name: str
    parameters: Optional[Dict[str, Any]] = None


class StoredProcedureResponse(BaseModel):
    """Response model for stored procedure execution"""

    success: bool
    database: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    affected_rows: Optional[int] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    databases: Dict[str, bool]
    connected_count: int
    total_count: int


# Dependency to get database pool manager
def get_db_pool() -> DatabasePoolManager:
    """Get the global database pool manager instance"""
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database service not initialized")
    return db_pool


# API Endpoints
@app.get("/", response_model=Dict[str, Any])
async def root():
    """Root endpoint"""
    if db_pool:
        connected_dbs = db_pool.get_connected_databases()
        return {
            "service": "Caravan Database Service",
            "status": "running",
            "databases": connected_dbs,
            "database_count": len(connected_dbs),
        }
    return {"service": "Caravan Database Service", "status": "running"}


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    if db_pool is None:
        return HealthResponse(
            status="unhealthy",
            databases={},
            connected_count=0,
            total_count=0,
        )

    status = db_pool.get_all_status()
    connected_count = sum(1 for connected in status.values() if connected)

    return HealthResponse(
        status="healthy" if connected_count > 0 else "unhealthy",
        databases=status,
        connected_count=connected_count,
        total_count=len(status),
    )


@app.post("/execute", response_model=StoredProcedureResponse)
async def execute_stored_procedure(
    request: StoredProcedureRequest, pool: DatabasePoolManager = Depends(get_db_pool)
):
    """
    Execute a stored procedure with optional parameters

    Args:
        request: StoredProcedureRequest with database, procedure name and parameters
        pool: DatabasePoolManager instance (injected)

    Returns:
        StoredProcedureResponse with execution results
    """
    try:
        # Get the specific database manager
        db_manager = pool.get_manager(request.database)

        if db_manager is None:
            logger.error(f"Database '{request.database}' not found or not connected")
            return StoredProcedureResponse(
                success=False,
                database=request.database,
                error=f"Database '{request.database}' not available",
            )

        logger.info(
            f"Executing stored procedure in '{request.database}': {request.procedure_name}"
        )

        result = db_manager.execute_stored_procedure(
            procedure_name=request.procedure_name, parameters=request.parameters or {}
        )

        if result["success"]:
            logger.info(
                f"Stored procedure executed successfully in '{request.database}': {request.procedure_name}"
            )
            return StoredProcedureResponse(
                success=True,
                database=request.database,
                data=result.get("data"),
                affected_rows=result.get("affected_rows"),
            )
        else:
            logger.error(f"Stored procedure execution failed: {result.get('error')}")
            return StoredProcedureResponse(
                success=False, database=request.database, error=result.get("error")
            )

    except Exception as e:
        logger.error(f"Error executing stored procedure: {str(e)}", exc_info=True)
        return StoredProcedureResponse(
            success=False, database=request.database, error=str(e)
        )


@app.post("/execute-query", response_model=StoredProcedureResponse)
async def execute_query(
    request: StoredProcedureRequest, pool: DatabasePoolManager = Depends(get_db_pool)
):
    """
    Execute a stored procedure that returns query results

    Args:
        request: StoredProcedureRequest with database, procedure name and parameters
        pool: DatabasePoolManager instance (injected)

    Returns:
        StoredProcedureResponse with query results
    """
    try:
        # Get the specific database manager
        db_manager = pool.get_manager(request.database)

        if db_manager is None:
            logger.error(f"Database '{request.database}' not found or not connected")
            return StoredProcedureResponse(
                success=False,
                database=request.database,
                error=f"Database '{request.database}' not available",
            )

        logger.info(
            f"Executing query procedure in '{request.database}': {request.procedure_name}"
        )

        result = db_manager.execute_query_procedure(
            procedure_name=request.procedure_name, parameters=request.parameters or {}
        )

        if result["success"]:
            logger.info(
                f"Query procedure executed successfully in '{request.database}': {request.procedure_name}"
            )
            return StoredProcedureResponse(
                success=True, database=request.database, data=result.get("data")
            )
        else:
            logger.error(f"Query procedure execution failed: {result.get('error')}")
            return StoredProcedureResponse(
                success=False, database=request.database, error=result.get("error")
            )

    except Exception as e:
        logger.error(f"Error executing query procedure: {str(e)}", exc_info=True)
        return StoredProcedureResponse(
            success=False, database=request.database, error=str(e)
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("DB_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("DB_SERVICE_PORT", "8080"))

    logger.info(f"Starting database service on {host}:{port}")

    uvicorn.run("main:app", host=host, port=port, log_level="info", reload=False)
