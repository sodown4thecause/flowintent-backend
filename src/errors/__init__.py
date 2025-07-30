"""Error handling module for the Natural Language Workflow Platform."""

from .base import (
    WorkflowPlatformError,
    ValidationError,
    AuthenticationError,
    IntegrationError,
    WorkflowExecutionError,
    DatabaseError,
    VectorStoreError,
    APIError
)

from .handlers import (
    GlobalErrorHandler,
    WorkflowErrorHandler,
    IntegrationErrorHandler
)

from .recovery import (
    ErrorRecoveryStrategy,
    RetryStrategy,
    FallbackStrategy,
    UserInterventionStrategy
)

__all__ = [
    # Base errors
    "WorkflowPlatformError",
    "ValidationError", 
    "AuthenticationError",
    "IntegrationError",
    "WorkflowExecutionError",
    "DatabaseError",
    "VectorStoreError",
    "APIError",
    
    # Error handlers
    "GlobalErrorHandler",
    "WorkflowErrorHandler", 
    "IntegrationErrorHandler",
    
    # Recovery strategies
    "ErrorRecoveryStrategy",
    "RetryStrategy",
    "FallbackStrategy",
    "UserInterventionStrategy"
]