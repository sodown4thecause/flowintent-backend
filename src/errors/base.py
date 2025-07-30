"""Base error classes for the Natural Language Workflow Platform."""

from typing import Dict, Any, Optional, List
from enum import Enum
import traceback
from datetime import datetime


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for classification."""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INTEGRATION = "integration"
    WORKFLOW_EXECUTION = "workflow_execution"
    DATABASE = "database"
    VECTOR_STORE = "vector_store"
    API = "api"
    NETWORK = "network"
    CONFIGURATION = "configuration"
    SYSTEM = "system"


class WorkflowPlatformError(Exception):
    """Base exception for all workflow platform errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN_ERROR",
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None,
        recoverable: bool = True,
        retry_after: Optional[int] = None,
        original_error: Optional[Exception] = None
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.user_message = user_message or self._generate_user_message()
        self.recoverable = recoverable
        self.retry_after = retry_after
        self.original_error = original_error
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc()
    
    def _generate_user_message(self) -> str:
        """Generate a user-friendly error message."""
        if self.category == ErrorCategory.VALIDATION:
            return "Please check your input and try again."
        elif self.category == ErrorCategory.AUTHENTICATION:
            return "Authentication failed. Please check your credentials."
        elif self.category == ErrorCategory.INTEGRATION:
            return "There was an issue connecting to an external service. Please try again later."
        elif self.category == ErrorCategory.WORKFLOW_EXECUTION:
            return "Your workflow encountered an issue during execution. We're working to resolve it."
        elif self.category == ErrorCategory.DATABASE:
            return "There was a temporary database issue. Please try again in a moment."
        else:
            return "An unexpected error occurred. Please try again or contact support if the issue persists."
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "user_message": self.user_message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "recoverable": self.recoverable,
            "retry_after": self.retry_after,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback,
            "original_error": str(self.original_error) if self.original_error else None
        }


class ValidationError(WorkflowPlatformError):
    """Error for validation failures."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            context={"field": field, "value": value},
            **kwargs
        )
        self.field = field
        self.value = value


class AuthenticationError(WorkflowPlatformError):
    """Error for authentication failures."""
    
    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.HIGH,
            context={"service": service},
            recoverable=True,
            **kwargs
        )
        self.service = service


class IntegrationError(WorkflowPlatformError):
    """Error for external service integration failures."""
    
    def __init__(
        self,
        message: str,
        service: str,
        operation: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="INTEGRATION_ERROR",
            category=ErrorCategory.INTEGRATION,
            severity=ErrorSeverity.MEDIUM,
            context={
                "service": service,
                "operation": operation,
                "status_code": status_code
            },
            **kwargs
        )
        self.service = service
        self.operation = operation
        self.status_code = status_code


class WorkflowExecutionError(WorkflowPlatformError):
    """Error for workflow execution failures."""
    
    def __init__(
        self,
        message: str,
        workflow_id: str,
        step_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="WORKFLOW_EXECUTION_ERROR",
            category=ErrorCategory.WORKFLOW_EXECUTION,
            severity=ErrorSeverity.HIGH,
            context={
                "workflow_id": workflow_id,
                "step_id": step_id,
                "execution_id": execution_id
            },
            **kwargs
        )
        self.workflow_id = workflow_id
        self.step_id = step_id
        self.execution_id = execution_id


class DatabaseError(WorkflowPlatformError):
    """Error for database operation failures."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.HIGH,
            context={"operation": operation, "table": table},
            **kwargs
        )
        self.operation = operation
        self.table = table


class VectorStoreError(WorkflowPlatformError):
    """Error for vector store operation failures."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        collection: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="VECTOR_STORE_ERROR",
            category=ErrorCategory.VECTOR_STORE,
            severity=ErrorSeverity.MEDIUM,
            context={"operation": operation, "collection": collection},
            **kwargs
        )
        self.operation = operation
        self.collection = collection


class APIError(WorkflowPlatformError):
    """Error for API operation failures."""
    
    def __init__(
        self,
        message: str,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="API_ERROR",
            category=ErrorCategory.API,
            severity=ErrorSeverity.MEDIUM,
            context={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code
            },
            **kwargs
        )
        self.endpoint = endpoint
        self.method = method
        self.status_code = status_code