# Understanding Log Levels in FloAI

FloAI uses standard Python logging levels to indicate the severity of logged messages. Here are the common levels used (from least to most severe):

- **DEBUG**: Detailed information for debugging purposes.
- **INFO**: Informational messages about the normal operation of the system.
- **WARNING**: Potential issues or unexpected conditions.
- **ERROR**: Errors that may have caused the system to malfunction.
- **CRITICAL**: Critical errors that have caused the system to crash.

By adjusting the log level, you can control how much information is logged and the verbosity of the output.

## Controlling Log Levels

FloAI provides multiple ways to control log levels:

### 1. Environment Variables for Log Level Control

Export environment variables to set the log level for specific components before running the application:

- `FLO_LOG_LEVEL_COMMON`: Controls the level for the "CommonLogs" logger.
  - CommonLogs: General-purpose logging used across the entire FloAI system. It captures broad, system-wide events and information.

- `FLO_LOG_LEVEL_BUILDER`: Controls the level for the "BuilderLogs" logger.
  - BuilderLogs: Specific to the process of building and configuring FloAI instances. It logs information about YAML parsing, component creation, and FloAI structure setup.

- `FLO_LOG_LEVEL_SESSION`: Controls the level for the "SessionLogs" logger. 
  - SessionLogs: Dedicated to logging session-specific information. It captures events and data related to individual FloAI sessions, including session creation, tool registration, and session-level operations.

These loggers allow for granular control over logging output in different parts of the FloAI system. By adjusting their levels independently, you can focus on debugging or monitoring specific aspects of FloAI's operation.

Example:

```bash
export FLO_LOG_LEVEL_COMMON=DEBUG
export FLO_LOG_LEVEL_BUILDER=INFO
export FLO_LOG_LEVEL_SESSION=WARNING
```

### 2. FloSession Creation

When creating a FloSession object, you can specify the desired log level:

```python
session = FloSession(llm, log_level="DEBUG")
```

This session will log messages at DEBUG level and above.

### 3. Flo Instance Creation

Similar to FloSession, you can set the log level when creating a Flo instance:

```python
flo = Flo.build(session, yaml_config, log_level="DEBUG")
```

This Flo instance will inherit the specified log level.

### 4. Global Log Level Change (Runtime)

You can dynamically change the global log level at runtime using the set_global_log_level function from flo_ai.common.logging_config:

```python
from flo_ai.common.logging_config import set_global_log_level

set_global_log_level("DEBUG")  # Set the global log level to DEBUG
```

This will affect all logging throughout the application.

### 5. Specific Logger Level Change (Runtime)

If you need to adjust the level for a specific logger, use the set_log_level method of the FloLogger class:

```python
from flo_ai.common.logging_config import FloLogger

FloLogger.set_log_level("COMMON", "DEBUG")  # Set COMMON logger to DEBUG level
```

## Best Practices

- **Environment variables**: Use these for setting default levels without modifying code, useful in different deployment environments.
- **Object creation**: This approach allows setting specific levels for individual sessions or Flo instances.
- **Runtime changes**: Use these methods for dynamic adjustments during program execution.