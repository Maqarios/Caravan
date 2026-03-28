# Caravan Database Service API Reference

## Overview

The Caravan Database Service is a FastAPI-based microservice that provides a REST API for executing SQL Server stored procedures with connection pooling, OUTPUT parameter support, and industry-standard error handling.

**Version**: 2.0.0  
**Base URL**: `http://db-service:8080` (Docker) or `http://localhost:8080` (Local)

## Architecture

- **Framework**: FastAPI 0.100+
- **Database Driver**: pyodbc (synchronous, appropriate for per-server bot scale)
- **Connection Pooling**: Thread-safe queue-based pooling (5-10 connections per database)
- **OUTPUT Parameters**: Industry-standard DECLARE + EXEC + SELECT with intelligent multi-result-set retrieval
- **Security**: Parameter validation, SQL injection prevention, type whitelisting

## Features

✅ **Smart Endpoint** - Auto-detects query vs execute procedures  
✅ **Connection Pooling** - Multiple connections per database for concurrent requests  
✅ **OUTPUT Parameters** - Industry-standard implementation with multi-result-set support  
✅ **Request Tracing** - Correlation IDs for distributed debugging  
✅ **Proper HTTP Status Codes** - 200, 400, 422, 503, 500  
✅ **Health Monitoring** - Real database connectivity tests  
✅ **Type Safety** - Comprehensive validation

---

## Endpoints

### 1. Root Endpoint

Get service information and status.

#### Request

```http
GET /
```

#### Response

```json
{
  "service": "Caravan Database Service",
  "version": "2.0.0",
  "status": "running",
  "databases": ["SRO_VT_ACCOUNT", "SRO_VT_SHARD", "SRO_VT_LOG"],
  "database_count": 3,
  "features": [
    "Connection pooling",
    "OUTPUT parameters",
    "Smart endpoint (auto-detect query vs execute)",
    "Proper HTTP status codes"
  ],
  "health": {
    "SRO_VT_ACCOUNT": {
      "database": "SRO_VT_ACCOUNT",
      "total_connections": 5,
      "healthy_connections": 5,
      "stale_connections": 0,
      "available_in_pool": 5
    }
  }
}
```

#### Status Codes

- `200 OK` - Service is running

---

### 2. Health Check

Check service and database health with actual connectivity tests.

#### Request

```http
GET /health
```

#### Response

```json
{
  "status": "healthy",
  "databases": {
    "SRO_VT_ACCOUNT": true,
    "SRO_VT_SHARD": true,
    "SRO_VT_LOG": false
  },
  "connected_count": 2,
  "total_count": 3,
  "pool_stats": {
    "SRO_VT_ACCOUNT": {
      "database": "SRO_VT_ACCOUNT",
      "total_connections": 5,
      "healthy_connections": 5,
      "stale_connections": 0,
      "available_in_pool": 4
    }
  }
}
```

#### Status Codes

- `200 OK` - Health check completed (check `status` field for actual health)
- `503 Service Unavailable` - Service not initialized

#### Notes

- Executes `sp_who` system procedure on each database to verify connectivity
- Returns detailed connection pool statistics
- `status` is `"healthy"` if at least one database is connected

---

### 3. Execute Procedure (Smart Endpoint)

Execute a stored procedure with automatic detection of query vs execute behavior.

#### Request

```http
POST /api/v1/execute
Content-Type: application/json
X-Request-ID: optional-correlation-id
```

```json
{
  "database": "SRO_VT_ACCOUNT",
  "procedure_name": "usp_AddUser",
  "parameters": {
    "StrUserID": "john_doe",
    "Password": "hashed_password",
    "Email": "john@example.com",
    "RegIP": "192.168.1.1"
  },
  "output_params": {
    "JID": "int",
    "Status": "varchar(20)"
  }
}
```

#### Request Fields

| Field            | Type   | Required | Description                                         |
| ---------------- | ------ | -------- | --------------------------------------------------- |
| `database`       | string | Yes      | Database name (must be configured in service)       |
| `procedure_name` | string | Yes      | Stored procedure name (supports `schema.procedure`) |
| `parameters`     | object | No       | Input parameters (key-value pairs)                  |
| `output_params`  | object | No       | OUTPUT parameters with SQL types                    |

#### Response (Execute - No Data)

When procedure doesn't return a result set:

```json
{
  "success": true,
  "database": "SRO_VT_ACCOUNT",
  "procedure_name": "usp_AddUser",
  "affected_rows": 1,
  "output_values": {
    "JID": 12345,
    "Status": "Created"
  }
}
```

#### Response (Query - Returns Data)

When procedure returns a result set:

```json
{
  "success": true,
  "database": "SRO_VT_ACCOUNT",
  "procedure_name": "usp_GetUsers",
  "data": [
    {
      "JID": 12345,
      "StrUserID": "john_doe",
      "Email": "john@example.com"
    },
    {
      "JID": 12346,
      "StrUserID": "jane_doe",
      "Email": "jane@example.com"
    }
  ],
  "row_count": 2,
  "output_values": {
    "TotalCount": 100
  }
}
```

#### Error Response

```json
{
  "detail": {
    "success": false,
    "error_code": "VALIDATION_ERROR",
    "message": "Procedure execution validation failed",
    "details": "Invalid procedure name: 'DROP TABLE'",
    "database": "SRO_VT_ACCOUNT",
    "procedure_name": "DROP TABLE"
  }
}
```

#### Status Codes

| Code                        | Meaning          | Description                             |
| --------------------------- | ---------------- | --------------------------------------- |
| `200 OK`                    | Success          | Procedure executed successfully         |
| `400 Bad Request`           | Invalid Database | Database not configured or name invalid |
| `422 Unprocessable Entity`  | Validation Error | Parameter/procedure validation failed   |
| `503 Service Unavailable`   | Database Down    | Database not connected                  |
| `500 Internal Server Error` | Execution Error  | Unexpected failure during execution     |

#### Response Headers

- `X-Request-ID` - Correlation ID for tracing
- `X-Response-Time` - Request duration (e.g., "0.123s")

#### Error Codes

| Error Code             | Description                                  |
| ---------------------- | -------------------------------------------- |
| `INVALID_DATABASE`     | Database name not in configured list         |
| `DATABASE_UNAVAILABLE` | Database connection not available            |
| `VALIDATION_ERROR`     | Input validation failed (name, type, format) |
| `EXECUTION_ERROR`      | Procedure execution failed                   |
| `INTERNAL_ERROR`       | Unexpected server error                      |

---

## Request/Response Models

### StoredProcedureRequest

```typescript
{
  database: string,           // Required: Database name
  procedure_name: string,     // Required: Procedure name (supports schema.proc)
  parameters: {               // Optional: Input parameters
    [key: string]: any
  },
  output_params: {            // Optional: OUTPUT parameters with SQL types
    [key: string]: string     // e.g., {"user_id": "int"}
  }
}
```

**Validation Rules:**
- `database`: Alphanumeric + underscore, starts with letter/underscore
- `procedure_name`: Same as database, or `schema.procedure` format
- `parameters`: Max 100 parameters
- `output_params`: SQL types must be in supported list

### ExecuteResponse

```typescript
{
  success: true,
  database: string,           // Database name
  procedure_name: string,     // Procedure name
  affected_rows: number,      // Number of rows affected
  output_values: {            // OUTPUT parameter values
    [key: string]: any
  }
}
```

### QueryResponse

```typescript
{
  success: true,
  database: string,           // Database name
  procedure_name: string,     // Procedure name
  data: Array<{               // Result rows
    [key: string]: any
  }>,
  row_count: number,          // Number of rows returned
  output_values: {            // OUTPUT parameter values
    [key: string]: any
  }
}
```

### ErrorResponse

```typescript
{
  success: false,
  error_code: string,         // Error identifier (see Error Codes)
  message: string,            // Human-readable error message
  details: string | null,     // Additional error details
  database: string | null,    // Database name if applicable
  procedure_name: string | null  // Procedure name if applicable
}
```

---

## Supported SQL Types (OUTPUT Parameters)

### Numeric Types
- `int`, `bigint`, `smallint`, `tinyint`, `bit`
- `decimal(p,s)`, `numeric(p,s)` - e.g., `decimal(10,2)`
- `float`, `real`
- `money`, `smallmoney`

### String Types
- `char(n)`, `varchar(n)`, `varchar(max)`
- `nchar(n)`, `nvarchar(n)`, `nvarchar(max)`
- `text`, `ntext`

### Date/Time Types
- `datetime`, `datetime2`, `date`, `time`

### Other Types
- `uniqueidentifier`
- `binary(n)`, `varbinary(n)`, `varbinary(max)`

---

## Usage Examples

### Example 1: Simple INSERT with Auto-Generated ID

**Request:**
```bash
curl -X POST http://localhost:8080/api/v1/execute \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: req-001" \
  -d '{
    "database": "SRO_VT_ACCOUNT",
    "procedure_name": "usp_AddUser",
    "parameters": {
      "StrUserID": "alice",
      "Password": "hashed_pass",
      "Email": "alice@example.com"
    },
    "output_params": {
      "JID": "int"
    }
  }'
```

**Response:**
```json
{
  "success": true,
  "database": "SRO_VT_ACCOUNT",
  "procedure_name": "usp_AddUser",
  "affected_rows": 1,
  "output_values": {
    "JID": 12345
  }
}
```

### Example 2: SELECT Query with Pagination

**Request:**
```bash
curl -X POST http://localhost:8080/api/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "database": "SRO_VT_ACCOUNT",
    "procedure_name": "usp_GetUsersPaginated",
    "parameters": {
      "PageNumber": 1,
      "PageSize": 10
    },
    "output_params": {
      "TotalCount": "int"
    }
  }'
```

**Response:**
```json
{
  "success": true,
  "database": "SRO_VT_ACCOUNT",
  "procedure_name": "usp_GetUsersPaginated",
  "data": [
    {"JID": 1, "StrUserID": "user1"},
    {"JID": 2, "StrUserID": "user2"}
  ],
  "row_count": 2,
  "output_values": {
    "TotalCount": 100
  }
}
```

### Example 3: Schema-Prefixed Procedure

**Request:**
```bash
curl -X POST http://localhost:8080/api/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "database": "SRO_VT_ACCOUNT",
    "procedure_name": "dbo.usp_ValidateUser",
    "parameters": {
      "Username": "bob",
      "PasswordHash": "hash123"
    },
    "output_params": {
      "IsValid": "bit",
      "UserID": "int"
    }
  }'
```

### Example 4: Error Handling

**Request:**
```bash
curl -X POST http://localhost:8080/api/v1/execute \
  -H "Content-Type: application/json" \
  -d '{
    "database": "NonExistentDB",
    "procedure_name": "usp_Test",
    "parameters": {}
  }'
```

**Response:** (HTTP 400)
```json
{
  "detail": {
    "success": false,
    "error_code": "INVALID_DATABASE",
    "message": "Database 'NonExistentDB' is not configured",
    "details": "Available databases: SRO_VT_ACCOUNT, SRO_VT_SHARD, SRO_VT_LOG",
    "database": "NonExistentDB"
  }
}
```

---

## Configuration

### Environment Variables

| Variable              | Required | Default | Description                       |
| --------------------- | -------- | ------- | --------------------------------- |
| `MSSQL_SERVER`        | Yes      | -       | SQL Server hostname or IP         |
| `MSSQL_PORT`          | No       | 1433    | SQL Server port                   |
| `MSSQL_USERNAME`      | Yes      | -       | Database username                 |
| `MSSQL_PASSWORD`      | Yes      | -       | Database password                 |
| `MSSQL_DATABASES`     | Yes      | -       | Comma-separated database names    |
| `DB_POOL_SIZE_PER_DB` | No       | 5       | Connections per database (1-50)   |
| `DB_SERVICE_HOST`     | No       | 0.0.0.0 | Service bind address              |
| `DB_SERVICE_PORT`     | No       | 8080    | Service port                      |
| `DB_LOG_LEVEL`        | No       | 20      | Logging level (10=DEBUG, 20=INFO) |

### Example Configuration

```bash
# .env file
MSSQL_SERVER=localhost
MSSQL_PORT=1433
MSSQL_USERNAME=sa
MSSQL_PASSWORD=YourPassword123
MSSQL_DATABASES=SRO_VT_ACCOUNT,SRO_VT_SHARD,SRO_VT_LOG
DB_POOL_SIZE_PER_DB=10
DB_LOG_LEVEL=20
```

---

## Best Practices

1. **Use Correlation IDs**: Always send `X-Request-ID` header for request tracing
2. **Check HTTP Status**: Don't assume 200 OK - handle 4xx/5xx appropriately
3. **Validate Responses**: Always check `success` field even on 200 OK
4. **Handle Timeouts**: Connection pool has 30s timeout - implement retries
5. **Monitor Health**: Poll `/health` endpoint to track database availability
6. **Schema Prefixes**: Use `dbo.procedure_name` for clarity when needed
7. **Type Accuracy**: Specify exact SQL types in `output_params`

---

## Security Considerations

### Input Validation

- **Procedure Names**: Validated with regex `^[a-zA-Z_][a-zA-Z0-9_]*$`
- **Parameter Names**: Same validation as procedure names
- **SQL Types**: Whitelist validation (see Supported SQL Types)
- **Database Names**: Checked against configured list
- **Parameter Count**: Limited to 100 per request

### SQL Injection Prevention

- Input parameters use positional placeholders (`?`)
- No user input concatenated into SQL strings
- OUTPUT parameter types validated before use
- Procedure names validated before execution

### Sensitive Data

- Parameter values NOT logged (prevents password/key exposure)
- Only parameter names and procedure names in logs
- Use environment variables for credentials (never hardcode)

---

## Troubleshooting

### Common Issues

#### 503 Service Unavailable

**Symptoms**: All requests return 503  
**Causes**:
- Database server not reachable
- Invalid credentials
- Firewall blocking connection

**Solutions**:
1. Check `/health` endpoint for detailed status
2. Verify `MSSQL_SERVER`, `MSSQL_USERNAME`, `MSSQL_PASSWORD`
3. Test database connectivity: `telnet $MSSQL_SERVER 1433`
4. Check service logs for connection errors

#### 422 Validation Error

**Symptoms**: Procedure name or parameters rejected  
**Causes**:
- Invalid characters in names
- Unsupported SQL type
- Too many parameters (>100)

**Solutions**:
1. Check error `details` field for specific failure
2. Ensure names match `^[a-zA-Z_][a-zA-Z0-9_]*$`
3. Verify SQL types against supported list
4. Reduce parameter count if needed

#### Output Parameters Not Returned

**Symptoms**: `output_values` is empty  
**Causes**:
- Stored procedure not setting OUTPUT parameters
- Incorrect SQL type specified
- Procedure syntax error

**Solutions**:
1. Test procedure directly in SQL Server
2. Verify `OUTPUT` keyword in procedure definition
3. Check SQL type matches actual parameter type
4. Review database service logs for warnings

---

## Monitoring

### Metrics to Track

- Request duration (via `X-Response-Time` header)
- Error rate by status code (400, 422, 503, 500)
- Connection pool utilization (via `/health` pool_stats)
- Database availability (via `/health` databases)

### Logging

All requests logged with:
- Correlation ID (`X-Request-ID`)
- HTTP method and path
- Status code
- Duration
- Error details (if applicable)

**Log Format:**
```
[correlation-id] METHOD /path - Status: 200 - Duration: 0.123s
```

---

## See Also

- [OUTPUT_PARAMETERS.md](OUTPUT_PARAMETERS.md) - OUTPUT Parameters Guide
- [DATABASE.md](DATABASE.md) - Database Configuration
- [../db/README.md](../db/README.md) - Service Architecture
