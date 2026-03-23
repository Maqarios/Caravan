# Database Service

The database service is a FastAPI-based microservice that handles all MSSQL database operations for the Caravan project. It provides a REST API for executing stored procedures and is designed to be used by both the bot and web services.

**Multi-Database Support**: The service can connect to multiple databases on the same SQL Server simultaneously, allowing you to separate game data, accounts, logs, etc.

## Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌────────────┐
│  Bot/Web    │  HTTP   │   Database       │  ODBC   │   MSSQL    │
│  Services   │────────>│   Service        │────────>│  Server    │
│             │         │  (Multi-DB Pool) │         │            │
└─────────────┘         └──────────────────┘         ├────────────┤
                                                      │ DB1: SHARD │
                                                      │ DB2: ACCT  │
                                                      │ DB3: LOG   │
                                                      └────────────┘
```

## Features

- **Multi-Database Support**: Connect to multiple databases simultaneously
- **Connection Management**: Automatic connection pooling and reconnection
- **Stored Procedure Execution**: Support for both query and non-query procedures
- **Error Handling**: Comprehensive error logging and graceful error responses
- **Health Checks**: Built-in health check endpoint showing status of all databases
- **Thread-Safe**: Safe for concurrent requests

## API Endpoints

### Health Check
```
GET /health
```
Returns the service health status and database connection state for all configured databases.

**Response:**
```json
{
  "status": "healthy",
  "databases": {
    "SRO_VT_SHARD": true,
    "SRO_VT_ACCOUNT": true,
    "SRO_VT_LOG": false
  },
  "connected_count": 2,
  "total_count": 3
}
```

### Execute Stored Procedure
```
POST /execute
```
Execute a stored procedure (INSERT, UPDATE, DELETE operations).

**Request:**
```json
{
  "database": "SRO_VT_ACCOUNT",
  "procedure_name": "sp_UpdateUser",
  "parameters": {
    "user_id": 123,
    "username": "player1"
  }
}
```

**Response:**
```json
{
  "success": true,
  "database": "SRO_VT_ACCOUNT",
  "affected_rows": 1
}
```

### Execute Query Procedure
```
POST /execute-query
```
Execute a stored procedure that returns data (SELECT operations).

**Request:**
```json
{
  "database": "SRO_VT_SHARD",
  "procedure_name": "sp_GetUserByID",
  "parameters": {
    "user_id": 123
  }
}
```

**Response:**
```json
{
  "success": true,
  "database": "SRO_VT_SHARD",
  "data": [
    {
      "user_id": 123,
      "username": "player1",
      "level": 50
    }
  ]
}
```

## Environment Variables

The following environment variables must be set:

```env
# Database connection (shared for all databases)
MSSQL_SERVER=your-server-host
MSSQL_DATABASES=SRO_VT_SHARD,SRO_VT_ACCOUNT,SRO_VT_LOG  # Comma-separated list
MSSQL_USERNAME=your-username
MSSQL_PASSWORD=your-password
MSSQL_PORT=1433

# Service configuration
DB_SERVICE_HOST=0.0.0.0
DB_SERVICE_PORT=8080
DB_SERVICE_URL=http://db:8080  # For clients (bot/web) to connect
```

**Configuration Notes:**
- `MSSQL_DATABASES`: Comma-separated list of database names (preferred for multi-database)
- `MSSQL_DATABASE`: Single database name (backward compatibility, falls back if MSSQL_DATABASES not set)
- The service connects to all databases on startup and maintains separate connections
- All databases must be on the same server and use the same credentials

## Using the Database Client

Both bot and web services can use the `DatabaseClient` class from the utils package:

### Synchronous Usage (Web/Flask)
```python
from utils import DatabaseClient

# Initialize client
db_client = DatabaseClient()

# Execute a stored procedure on a specific database
result = db_client.execute_procedure(
    database="SRO_VT_ACCOUNT",
    procedure_name="sp_UpdateUser",
    parameters={"user_id": 123, "username": "player1"}
)

if result["success"]:
    print(f"Updated {result['affected_rows']} rows")
else:
    print(f"Error: {result['error']}")

# Execute a query on a specific database
result = db_client.execute_query(
    database="SRO_VT_SHARD",
    procedure_name="sp_GetUserByID",
    parameters={"user_id": 123}
)

if result["success"]:
    for row in result["data"]:
        print(row)
```

### Asynchronous Usage (Bot/Discord.py)
```python
from utils import DatabaseClient

# Initialize client
db_client = DatabaseClient()

# Execute a stored procedure asynchronously
result = await db_client.async_execute_procedure(
    database="SRO_VT_ACCOUNT",
    procedure_name="sp_UpdateUser",
    parameters={"user_id": 123, "username": "player1"}
)

if result["success"]:
    print(f"Updated {result['affected_rows']} rows")

# Execute a query asynchronously
result = await db_client.async_execute_query(
    database="SRO_VT_SHARD",
    procedure_name="sp_GetUserByID",
    parameters={"user_id": 123}
)

if result["success"]:
    for row in result["data"]:
        print(row)
```

### Multi-Database Example
```python
# Query from different databases in the same application
account_result = await db_client.async_execute_query(
    database="SRO_VT_ACCOUNT",
    procedure_name="sp_GetAccount",
    parameters={"username": "player1"}
)

shard_result = await db_client.async_execute_query(
    database="SRO_VT_SHARD",
    procedure_name="sp_GetCharacter",
    parameters={"char_id": 456}
)

log_result = await db_client.async_execute_procedure(
    database="SRO_VT_LOG",
    procedure_name="sp_LogAction",
    parameters={"action": "login", "user_id": 123}
)
```

## Development

### Local Testing

Run the service locally:
```bash
# Activate virtual environment
source .venv/bin/activate

# Run the service
python db/main.py
```

The service will start on `http://localhost:8080` by default.

**Check service status:**
```bash
# Health check
curl http://localhost:8080/health

# Service info
curl http://localhost:8080/
```

### Docker

Build and run with Docker Compose:
```bash
# Build and start
docker-compose up -d --build db

# View logs
docker-compose logs -f db

# Check health
docker-compose exec db curl http://localhost:8080/health
```

## Error Handling

All database operations return a consistent response format:

**Success (Query):**
```json
{
  "success": true,
  "database": "SRO_VT_SHARD",
  "data": [...]
}
```

**Success (Modification):**
```json
{
  "success": true,
  "database": "SRO_VT_ACCOUNT",
  "affected_rows": 1
}
```

**Failure:**
```json
{
  "success": false,
  "database": "SRO_VT_ACCOUNT",
  "error": "Error message here"
}
```

## Logging

Logs are written to `/app/logs/db.log` and include:
- Database service startup and connection status
- Connection status for each database
- Stored procedure execution (with database name)
- Errors and exceptions with full stack traces
- Shutdown events

All logs use the shared logging utility from the `utils` package.

## Security Considerations

1. **Connection String**: Never log or expose the full connection string
2. **SQL Injection**: Using parameterized stored procedures prevents SQL injection
3. **Authentication**: Consider adding API key authentication for production
4. **Network**: Service should only be accessible within the Docker network
5. **Encryption**: TrustServerCertificate is enabled for development; use proper SSL in production

## Future Enhancements

- [ ] Connection pooling with multiple connections
- [ ] Query result caching
- [ ] Metrics and monitoring endpoints
- [ ] Rate limiting
- [ ] Authentication/authorization
- [ ] Query timeout configuration
- [ ] Batch operations support
