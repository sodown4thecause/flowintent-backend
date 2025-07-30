"""Error handlers for the Natural Language Workflow Platform."""

import logging
import asyncio
from typing import Any, Callable, Dict, List, Optional, Union
from functools import wraps
from datetime import datetime

from .base import (
    WorkflowPlatformError,
    ErrorCategory,
    ErrorSeverity,
    ValidationError,
    AuthenticationError,
    IntegrationError,
    WorkflowExecutionError,
    DatabaseError,
    VectorStoreError,
    APIError
)
from .recovery import (
    ErrorRecoveryStrategy,
    RecoveryResult,
    create_default_recovery_strategy
)

logger = logging.getLogger(__name__)


class GlobalErrorHandler:
    """Global error handler for the workflow platform."""
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.recovery_strategies: Dict[ErrorCategory, ErrorRecoveryStrategy] = {}
        self.error_callbacks: List[Callable] = []
        self.setup_default_strategies()
    
    def setup_default_strategies(self):
        """Set up default recovery strategies for each error category."""
        for category in ErrorCategory:
            self.recovery_strategies[category] = create_default_recovery_strategy(category)
    
    def register_recovery_strategy(
        self,
        category: ErrorCategory,
        strategy: ErrorRecoveryStrategy
    ):
        """Register a custom recovery strategy for an error category."""
        self.recovery_strategies[category] = strategy
    
    def add_error_callback(self, callback: Callable):
        """Add a callback to be called when errors occur."""
        self.error_callbacks.append(callback)
    
    async def handle_error(
        self,
        error: Exception,
        context: Dict[str, Any] = None,
        original_function: Optional[Callable] = None,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Handle an error with appropriate recovery strategy."""
        context = context or {}
        
        # Convert to WorkflowPlatformError if needed
        if not isinstance(error, WorkflowPlatformError):
            error = self._convert_to_platform_error(error, context)
        
        # Log the error
        await self._log_error(error, context)
        
        # Update error counts
        self._update_error_counts(error)
        
        # Notify callbacks
        await self._notify_callbacks(error, context)
        
        # Attempt recovery if function provided
        if original_function:
            return await self._attempt_recovery(
                error, context, original_function, *args, **kwargs
            )
        
        return RecoveryResult.FAILURE, None
    
    def _convert_to_platform_error(
        self,
        error: Exception,
        context: Dict[str, Any]
    ) -> WorkflowPlatformError:
        """Convert a generic exception to a WorkflowPlatformError."""
        error_type = type(error).__name__
        
        # Map common exceptions to platform errors
        if "validation" in str(error).lower() or "invalid" in str(error).lower():
            return ValidationError(
                message=str(error),
                original_error=error,
                context=context
            )
        elif "auth" in str(error).lower() or "permission" in str(error).lower():
            return AuthenticationError(
                message=str(error),
                original_error=error,
                context=context
            )
        elif "connection" in str(error).lower() or "network" in str(error).lower():
            return IntegrationError(
                message=str(error),
                service="unknown",
                original_error=error,
                context=context
            )
        elif "database" in str(error).lower() or "sql" in str(error).lower():
            return DatabaseError(
                message=str(error),
                original_error=error,
                context=context
            )
        else:
            return WorkflowPlatformError(
                message=str(error),
                error_code=f"CONVERTED_{error_type.upper()}",
                original_error=error,
                context=context
            )
    
    async def _log_error(self, error: WorkflowPlatformError, context: Dict[str, Any]):
        """Log the error with appropriate level."""
        log_data = {
            "error_code": error.error_code,
            "category": error.category.value,
            "severity": error.severity.value,
            "message": error.message,
            "context": context,
            "timestamp": error.timestamp.isoformat()
        }
        
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical("Critical error occurred", extra=log_data)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error("High severity error occurred", extra=log_data)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning("Medium severity error occurred", extra=log_data)
        else:
            logger.info("Low severity error occurred", extra=log_data)
    
    def _update_error_counts(self, error: WorkflowPlatformError):
        """Update error occurrence counts."""
        key = f"{error.category.value}:{error.error_code}"
        self.error_counts[key] = self.error_counts.get(key, 0) + 1
    
    async def _notify_callbacks(self, error: WorkflowPlatformError, context: Dict[str, Any]):
        """Notify registered error callbacks."""
        for callback in self.error_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error, context)
                else:
                    callback(error, context)
            except Exception as e:
                logger.error(f"Error callback failed: {e}")
    
    async def _attempt_recovery(
        self,
        error: WorkflowPlatformError,
        context: Dict[str, Any],
        original_function: Callable,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Attempt to recover from the error."""
        strategy = self.recovery_strategies.get(error.category)
        
        if not strategy:
            logger.warning(f"No recovery strategy for category: {error.category}")
            return RecoveryResult.FAILURE, None
        
        try:
            return await strategy.recover(
                error, context, original_function, *args, **kwargs
            )
        except Exception as e:
            logger.error(f"Recovery strategy failed: {e}")
            return RecoveryResult.FAILURE, None
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics."""
        return {
            "error_counts": self.error_counts.copy(),
            "total_errors": sum(self.error_counts.values()),
            "categories": list(set(
                key.split(":")[0] for key in self.error_counts.keys()
            ))
        }


class WorkflowErrorHandler:
    """Specialized error handler for workflow execution errors."""
    
    def __init__(self, global_handler: GlobalErrorHandler):
        self.global_handler = global_handler
        self.workflow_errors: Dict[str, List[WorkflowPlatformError]] = {}
    
    async def handle_workflow_error(
        self,
        error: Exception,
        workflow_id: str,
        step_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> tuple[RecoveryResult, Any]:
        """Handle workflow-specific errors."""
        context = context or {}
        context.update({
            "workflow_id": workflow_id,
            "step_id": step_id,
            "execution_id": execution_id
        })
        
        # Convert to workflow execution error if needed
        if not isinstance(error, WorkflowExecutionError):
            error = WorkflowExecutionError(
                message=str(error),
                workflow_id=workflow_id,
                step_id=step_id,
                execution_id=execution_id,
                original_error=error if isinstance(error, Exception) else None
            )
        
        # Track workflow errors
        if workflow_id not in self.workflow_errors:
            self.workflow_errors[workflow_id] = []
        self.workflow_errors[workflow_id].append(error)
        
        # Use global handler for recovery
        return await self.global_handler.handle_error(error, context)
    
    def get_workflow_errors(self, workflow_id: str) -> List[WorkflowPlatformError]:
        """Get errors for a specific workflow."""
        return self.workflow_errors.get(workflow_id, [])
    
    def clear_workflow_errors(self, workflow_id: str):
        """Clear errors for a specific workflow."""
        if workflow_id in self.workflow_errors:
            del self.workflow_errors[workflow_id]


class IntegrationErrorHandler:
    """Specialized error handler for integration errors."""
    
    def __init__(self, global_handler: GlobalErrorHandler):
        self.global_handler = global_handler
        self.service_errors: Dict[str, List[IntegrationError]] = {}
        self.service_status: Dict[str, str] = {}
    
    async def handle_integration_error(
        self,
        error: Exception,
        service: str,
        operation: Optional[str] = None,
        context: Dict[str, Any] = None
    ) -> tuple[RecoveryResult, Any]:
        """Handle integration-specific errors."""
        context = context or {}
        context.update({
            "service": service,
            "operation": operation
        })
        
        # Convert to integration error if needed
        if not isinstance(error, IntegrationError):
            error = IntegrationError(
                message=str(error),
                service=service,
                operation=operation,
                original_error=error if isinstance(error, Exception) else None
            )
        
        # Track service errors
        if service not in self.service_errors:
            self.service_errors[service] = []
        self.service_errors[service].append(error)
        
        # Update service status
        self.service_status[service] = "error"
        
        # Use global handler for recovery
        result, value = await self.global_handler.handle_error(error, context)
        
        # Update service status based on recovery result
        if result == RecoveryResult.SUCCESS:
            self.service_status[service] = "healthy"
        
        return result, value
    
    def get_service_status(self, service: str) -> str:
        """Get the current status of a service."""
        return self.service_status.get(service, "unknown")
    
    def get_service_errors(self, service: str) -> List[IntegrationError]:
        """Get errors for a specific service."""
        return self.service_errors.get(service, [])
    
    def mark_service_healthy(self, service: str):
        """Mark a service as healthy."""
        self.service_status[service] = "healthy"


# Decorator for automatic error handling
def handle_errors(
    handler: Optional[GlobalErrorHandler] = None,
    category: Optional[ErrorCategory] = None,
    context: Optional[Dict[str, Any]] = None
):
    """Decorator to automatically handle errors in functions."""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_handler = handler or GlobalErrorHandler()
                error_context = context or {}
                
                result, value = await error_handler.handle_error(
                    e, error_context, func, *args, **kwargs
                )
                
                if result == RecoveryResult.SUCCESS:
                    return value
                elif result == RecoveryResult.USER_INTERVENTION:
                    raise WorkflowPlatformError(
                        message="User intervention required",
                        error_code="USER_INTERVENTION_REQUIRED",
                        context=value
                    )
                else:
                    raise e
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # For sync functions, just convert to platform error
                if not isinstance(e, WorkflowPlatformError):
                    error_handler = handler or GlobalErrorHandler()
                    e = error_handler._convert_to_platform_error(e, context or {})
                raise e
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


# Global error handler instance
global_error_handler = GlobalErrorHandler()