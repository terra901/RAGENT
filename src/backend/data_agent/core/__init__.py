"""Core application infrastructure package.

Import concrete modules directly, for example:
- data_agent.core.config
- data_agent.core.logging
- data_agent.core.security
- data_agent.core.migrations

Keeping this package initializer light avoids pulling FastAPI middleware
dependencies when callers only need settings or logging.
"""
