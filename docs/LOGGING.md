# Caravan Logging System

Comprehensive logging documentation for bot and web applications.

## Overview

The Caravan logging utility provides:
- ✅ **Rotating file handlers** (10MB per file, 5 backups)
- ✅ **Separate logs** for bot (`bot.log`) and web (`web.log`)
- ✅ **Console output** for real-time monitoring
- ✅ **Structured format** with timestamps, levels, and context
- ✅ **Automatic log directory** creation

## Quick Start

### Bot Usage

```python
from utils.logger import get_logger

logger = get_logger('bot')

logger.debug("Debug information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
logger.critical("Critical failure")
```

### Web Usage

```python
from utils.logger import get_logger

logger = get_logger('web')

logger.info("Web server started on port 5000")
logger.error("Database connection failed", exc_info=True)
```

## Log Format

```
YYYY-MM-DD HH:MM:SS - logger_name - LEVEL - module:function:line - message
```

**Example:**
```
2026-03-21 23:10:27 - caravan.bot - INFO - main:on_ready:95 - Bot is ready!
```

## Log Locations

All logs are stored in the `logs/` directory at the project root:

```
caravan/
├── logs/
│   ├── bot.log          # Current bot logs
│   ├── bot.log.1        # Previous rotation
│   ├── bot.log.2        # Older rotation
│   ├── web.log          # Current web logs
│   └── web.log.1        # Previous rotation
```

## Rotation Behavior

- **Max file size:** 10MB
- **Backup count:** 5 files
- **Total storage:** ~60MB per application (10MB × 6 files)

When `bot.log` reaches 10MB:
1. `bot.log` → `bot.log.1`
2. `bot.log.1` → `bot.log.2`
3. ... continues to `bot.log.5`
4. `bot.log.5` is deleted
5. New `bot.log` is created

## Advanced Usage

### Change Log Level Dynamically

```python
from utils.logger import get_logger, set_log_level
import logging

logger = get_logger('bot')

# Enable debug logging
set_log_level('bot', logging.DEBUG)

# Back to normal
set_log_level('bot', logging.INFO)
```

### Discord.py Integration

```python
from utils.logger import setup_discord_logging
import logging

# Setup discord.py library logging
setup_discord_logging(logging.WARNING)  # Only show warnings/errors
```

### Exception Logging

```python
try:
    result = await risky_operation()
except Exception as e:
    logger.error("Operation failed", exc_info=True)  # Includes stack trace
```

## Log Levels

| Level      | When to Use                                        |
| ---------- | -------------------------------------------------- |
| `DEBUG`    | Detailed diagnostic information (development)      |
| `INFO`     | General informational messages (normal operations) |
| `WARNING`  | Warning messages (potential issues)                |
| `ERROR`    | Error messages (operation failed)                  |
| `CRITICAL` | Critical failures (system shutdown)                |

## Best Practices

### ✅ DO

```python
# Include context in messages
logger.info(f"{ctx.author} used command: {ctx.command}")

# Log exceptions with stack traces
logger.error("Database error", exc_info=True)

# Use appropriate log levels
logger.debug("Processing item 42")  # Development only
logger.info("User logged in")       # Normal operation
logger.error("Failed to save data") # Error occurred
```

### ❌ DON'T

```python
# Don't log sensitive data
logger.info(f"User password: {password}")  # NEVER DO THIS

# Don't use INFO for debug messages
logger.info("Loop iteration 1")  # Use DEBUG instead

# Don't log without context
logger.error("Error occurred")  # What error? Where?
```

## Environment Variables (Optional)

```bash
# Set default log level (default: INFO)
LOG_LEVEL=DEBUG
```

## Monitoring Logs

### Real-time Monitoring (Linux)

```bash
# Watch bot logs in real-time
tail -f logs/bot.log

# Watch web logs
tail -f logs/web.log

# Watch both
tail -f logs/*.log
```

### Search Logs

```bash
# Find all errors
grep "ERROR" logs/bot.log

# Find specific user actions
grep "username" logs/bot.log

# Count warnings
grep -c "WARNING" logs/bot.log
```

## Integration with Docker

Logs are mounted as volumes in Docker Compose:

```yaml
volumes:
  - ./logs:/app/logs
```

This allows logs to persist even when containers restart.

## Troubleshooting

### Logs not appearing?

1. Check if `logs/` directory exists
2. Verify file permissions
3. Ensure logger is initialized: `logger = get_logger('bot')`

### Logs too verbose?

```python
# Reduce noise from discord.py
setup_discord_logging(logging.WARNING)
```

### Want structured JSON logs?

Modify `LOG_FORMAT` in `utils/logger.py`:

```python
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        return json.dumps(log_data)
```

## Performance Considerations

- Logging is asynchronous-safe (doesn't block bot)
- File I/O is buffered for efficiency
- Rotation happens automatically without blocking
- Console output can be disabled if needed

## Support

For issues or questions about logging:
1. Check this documentation
2. Review `utils/logger.py` source code
3. Test with `python3 utils/logger.py`
