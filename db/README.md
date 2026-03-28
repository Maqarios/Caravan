# Caravan Database Service

Industry-standard microservice for SQL Server stored procedure execution with connection pooling, OUTPUT parameter support, and comprehensive error handling.

## Overview

The Database Service is a FastAPI-based microservice that provides a REST API for executing SQL Server stored procedures. It's designed specifically for the Caravan project's per-server Discord bot architecture, using synchronous pyodbc with connection pooling for optimal performance at this scale.

### Key Features

- ✅ **Connection Pooling**: Thread-safe queue-based pooling (5-10 connections per database)
- ✅ **OUTPUT Parameters**: Industry-standard DECLARE + EXEC + SELECT pattern
- ✅ **Smart Endpoint**: Auto-detects query vs execute procedures
- ✅ **Proper HTTP Status Codes**: 200, 400, 422, 503, 500 with structured errors
- ✅ **Request Tracing**: Correlation IDs (X-Request-ID) for distributed debugging
- ✅ **Input Validation**: Comprehensive validation to prevent SQL injection
- ✅ **Health Monitoring**: Real database connectivity tests
- ✅ **Type Safety**: SQL type whitelist validation

## Architecture

```
db/
├── main.py              # FastAPI application & endpoints
├── db_manager.py        # Database connection manager (single connection)
├── db_pool.py           # Connection pool manager (multiple connections)
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container image definition
└── README.md           # This file
```

### Design Decisions

**Why Synchronous (pyodbc)?**
- Per-server Discord bot doesn't need async scalability of multi-guild bots
- Simpler implementation and debugging
- Connection pooling handles concurrency effectively at this scale
- Proven reliability for stored procedure execution

**Why Connection Pooling?**
- Multiple simultaneous bot commands can execute concurrently
- Prevents connection exhaustion under load
- Automatic connection health management
- Thread-safe queue ensures proper resource management

**Why DECLARE + EXEC + SELECT?**
- Industry standard pattern for pyodbc + SQL Server
- Reliable OUTPUT parameter retrieval across all result sets
- Works with all SQL Server data types
- Prevents SQL injection via positional parameters
- Handles complex procedures with multiple intermediate result sets

## Quick Start

### Local Development

1. **Install Dependencies**
```bash
cd db/
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure Environment**
```bash
cp ../.env.example .env
# Edit .env with your SQL Server credentials
```

3. **Run Service**
```bash
python main.py
```

Service runs on `http://localhost:8080`

### Docker Compose

```bash
# From project root
docker compose up db
```

Service runs on `http://db:8080` (internal) or `http://localhost:8080` (host)

## Configuration

### Environment Variables

| Variable              | Required | Default | Description                               |
| --------------------- | -------- | ------- | ----------------------------------------- |
| `MSSQL_SERVER`        | Yes      | -       | SQL Server hostname/IP                    |
| `MSSQL_PORT`          | No       | 1433    | SQL Server port                           |
| `MSSQL_USERNAME`      | Yes      | -       | Database username                         |
| `MSSQL_PASSWORD`      | Yes      | -       | Database password                         |
| `MSSQL_DATABASES`     | Yes      | -       | Comma-separated database names            |
| `DB_POOL_SIZE_PER_DB` | No       | 5       | Connections per database (1-50)           |
| `DB_SERVICE_HOST`     | No       | 0.0.0.0 | Service bind address                      |
| `DB_SERVICE_PORT`     | No       | 8080    | Service port                              |
| `DB_LOG_LEVEL`        | No       | 20      | Log level (10=DEBUG, 20=INFO, 30=WARNING) |

### Example Configuration

```bash
# .env
MSSQL_SERVER=localhost
MSSQL_PORT=1433
MSSQL_USERNAME=sa
MSSQL_PASSWORD=YourPassword123
MSSQL_DATABASES=SRO_VT_ACCOUNT,SRO_VT_SHARD,SRO_VT_LOG
DB_POOL_SIZE_PER_DB=10
DB_LOG_LEVEL=20
```

## API Usage

### Execute Procedure

```bash
curl -X POST http://localhost:8080/api/v1/execute \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: req-12345" \
  -d '{
    "database": "SRO_VT_ACCOUNT",
    "procedure_name": "usp_AddUser",
    "parameters": {
      "StrUserID": "john_doe",
      "Password": "hashed_pass",
      "Email": "john@example.com"
    },
    "output_params": {
      "JID": "int"
    }
  }'
```

### Health Check

```bash
curl http://localhost:8080/health
```

### Service Info

```bash
curl http://localhost:8080/
```

## Connection Pooling

### How It Works

1. **Initialization**: Service creates N connections per database on startup
2. **Request Handling**: Each request gets a connection from the pool's queue
3. **Connection Reuse**: After use, connection returns to pool for next request
4. **Health Monitoring**: Periodic checks ensure connections are healthy
5. **Auto-Reconnect**: Stale connections automatically refreshed

### Pool Configuration

```python
# Default: 5 connections per database
db_pool = DatabasePoolManager(
    server="localhost",
    databases=["DB1", "DB2"],
    pool_size_per_db=5  # Configurable
)
```

**Recommended Pool Sizes:**
- **Light usage** (< 10 concurrent requests): 5 connections
- **Moderate usage** (10-50 concurrent requests): 10 connections
- **Heavy usage** (50+ concurrent requests): 20 connections

### pool vs Manager

```python
# Connection Pool (NEW - multiple connections)
with pool.get_connection("SRO_VT_ACCOUNT") as manager:
    result = manager.execute_stored_procedure(...)

# Pooled Manager (Backward compatible wrapper)
pooled_manager = pool.get_manager("SRO_VT_ACCOUNT")
result = pooled_manager.execute_stored_procedure(...)
# Automatically gets/returns connection from pool
```

## Security

### Input Validation

All inputs validated before execution:

1. **Database Names**: Alphanumeric + underscore, starts with letter/underscore
2. **Procedure Names**: Same rules, supports `schema.procedure` format
3. **Parameter Names**: Same rules as database names
4. **SQL Types**: Whitelist of known SQL Server types only
5. **Parameter Count**: Maximum 100 parameters per request

### SQL Injection Prevention

- Input parameters use positional placeholders (`?`)
- No user input concatenated into SQL strings
- OUTPUT parameter types validated against whitelist
- Procedure names validated before building SQL

### Secure Practices

- Credentials from environment variables only
- Parameter values NOT logged (prevents exposure)
- Connection pooling prevents resource exhaustion
- Proper error messages (no SQL details exposed)

## Monitoring & Debugging

### Request Tracing

Every request gets a correlation ID:

```bash
# Send with request
curl -H "X-Request-ID: my-trace-id" ...

# Received in response
X-Request-ID: my-trace-id
X-Response-Time: 0.123s
```

Logs include correlation ID:
```
[my-trace-id] POST /api/v1/execute - Status: 200 - Duration: 0.123s
```

### Health Monitoring

```bash
curl http://localhost:8080/health
```

Returns:
- Connection status per database
- Pool statistics (total, healthy, available connections)
- Test query execution results

### Log Levels

Set `DB_LOG_LEVEL`:
- `10` - DEBUG: SQL statements, connection events
- `20` - INFO: Request/response, procedure executions (default)
- `30` - WARNING: Connection issues, validation failures
- `40` - ERROR: Execution failures, exceptions

## Development

### Running Tests

```bash
# TODO: Add test suite
pytest tests/
```

### Code Structure

**main.py**
- FastAPI application setup
- API endpoint definitions
- Request/response models
- Middleware (correlation ID, logging)

**db_manager.py**
- Single database connection management
- Stored procedure execution
- OUTPUT parameter handling
- Validation logic

**db_pool.py**
- Connection pool implementation
- Thread-safe queue management
- Health monitoring
- Pooled manager wrapper

### Adding New Features

1. **New Endpoint**: Add to `main.py`
2. **New Validation**: Add to `db_manager.py` validators
3. **Pool Logic**: Modify `db_pool.py` ConnectionPool class

## Troubleshooting

### Service Won't Start

**Error**: `Missing required environment variables`  
**Solution**: Verify `MSSQL_SERVER`, `MSSQL_USERNAME`, `MSSQL_PASSWORD` set

**Error**: `Failed to establish any database connections`  
**Solution**: Check database server is running, credentials correct, firewall allows connection

### Slow Response Times

**Symptom**: Requests taking >1 second  
**Causes**:
- Pool exhausted (all connections in use)
- Stored procedure performance issues
- Network latency

**Solutions**:
1. Increase `DB_POOL_SIZE_PER_DB`
2. Optimize stored procedures
3. Check `/health` for pool utilization

### Connection Pool Timeout

**Error**: `Connection pool timeout - no connections available`  
**Cause**: All connections busy, waited 30s

**Solutions**:
1. Increase pool size
2. Optimize procedure execution time
3. Check for connection leaks (should auto-recover)

### Output Parameters Empty

**Symptom**: `output_values` returns empty dict  
**Causes**:
- Procedure not setting OUTPUT parameters
- Incorrect SQL type specified
- Procedure execution failed
- Column names in SELECT don't match expected output parameter names

**Solutions**:
1. Test procedure in SQL Server Management Studio
2. Verify OUTPUT keyword in procedure definition
3. Check SQL type matches parameter type
4. Ensure SELECT statement includes all output parameters
5. Review logs for specific errors

**Note**: The service automatically iterates through all result sets returned by the stored procedure to find the one containing your output parameters. This handles procedures that return multiple result sets (e.g., status codes, intermediate results) before the output parameters.

## Performance

### Benchmarks

Typical performance (on standard hardware):

- **Simple INSERT**: 10-50ms
- **SELECT with 100 rows**: 20-100ms
- **Complex procedure**: 50-500ms (depends on procedure)

Connection pool overhead: **<1ms** per request

### Optimization Tips

1. **Increase Pool Size**: More concurrent requests
2. **Optimize Procedures**: Faster execution = more throughput
3. **Use Indexes**: Stored procedure performance critical
4. **Monitor Health**: Track pool utilization

## Migration from v1.x

### Breaking Changes

1. **Endpoints Merged**: Use `/api/v1/execute` instead of `/execute` or `/execute-query`
2. **HTTP Status Codes**: Now uses 4xx/5xx instead of always 200
3. **Response Format**: Separate `ExecuteResponse` and `QueryResponse`
4. **Error Structure**: Errors have `error_code` field

### Migration Guide

**Old (v1.x):**
```python
response = requests.post("http://db:8080/execute", json=request_data)
if response.json()["success"]:
    # Handle success
```

**New (v2.0):**
```python
response = requests.post("http://db:8080/api/v1/execute", json=request_data)
if response.status_code == 200:
    data = response.json()
    if "data" in data:  # QueryResponse
        rows = data["data"]
    else:  # ExecuteResponse
        affected = data["affected_rows"]
elif response.status_code == 400:
    error = response.json()["detail"]
    # Handle bad request
```

## OUTPUT Parameter Implementation

### How It Works

The service uses the industry-standard **DECLARE + EXEC + SELECT** pattern:

```sql
DECLARE @JID int;
DECLARE @Status varchar(20);
EXEC usp_AddUser @username = ?, @email = ?, @JID = @JID OUTPUT, @Status = @Status OUTPUT;
SELECT @JID AS JID, @Status AS Status;
```

### Multiple Result Set Handling

The service intelligently handles stored procedures that return multiple result sets:

1. **Procedure Execution**: Your procedure may return 0+ result sets (e.g., status codes, intermediate data)
2. **Output Parameters**: Our SELECT statement appends the output parameters as the final result set
3. **Smart Retrieval**: Service iterates through ALL result sets to find the one matching your output parameter names
4. **Type Safety**: Column names must match the output parameter names you specified (case-insensitive)

**Example Scenario:**
```sql
-- Stored procedure that returns -1 on failure, success data otherwise
CREATE PROCEDURE usp_AddUser (@username VARCHAR(50), @JID INT OUTPUT)
AS
BEGIN
  IF EXISTS (SELECT 1 FROM Users WHERE Username = @username)
    RETURN -1;  -- Creates a result set with return value
  
  INSERT INTO Users (Username) VALUES (@username);
  SET @JID = SCOPE_IDENTITY();
END
```

The service automatically skips the RETURN value result set and finds the SELECT containing `JID`.

### Supported Scenarios

✅ Procedure with no result sets (only output params)  
✅ Procedure with single result set + output params  
✅ Procedure with multiple result sets + output params  
✅ Query procedure (data returned) + output params  
✅ Procedures with RETURN statements and output params  

## Documentation

- **[DB_SERVICE_API.md](../docs/DB_SERVICE_API.md)** - Complete API reference
- **[DATABASE.md](../docs/DATABASE.md)** - Database configuration
- **[LOGGING.md](../docs/LOGGING.md)** - Logging configuration

## Contributing

When contributing to this service:

1. Follow industry standards (documented in user memory)
2. Maintain security validations
3. Add tests for new features
4. Update documentation
5. Keep logging comprehensive but not verbose

## License

See [LICENSE](../LICENSE) file in project root.

## Version History

### v2.0.0 (Current)
- Added connection pooling
- Merged endpoints into smart `/api/v1/execute`
- Implemented proper HTTP status codes
- Added request correlation IDs
- Enhanced health checks
- Comprehensive validation
- Improved error handling
- **Robust output parameter retrieval** - Handles multiple result sets automatically

### v1.0.0 (Legacy)
- Basic stored procedure execution
- Separate `/execute` and `/execute-query` endpoints
- Single connection per database
- OUTPUT parameter support
