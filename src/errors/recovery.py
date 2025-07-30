"""Error recovery strategies for the Natural Language Workflow Platform."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, List, Union
from enum import Enum
import random
from datetime import datetime, timedelta

from .base import WorkflowPlatformError, ErrorSeverity, ErrorCategory

logger = logging.getLogger(__name__)


class RecoveryResult(str, Enum):
    """Results of recovery attempts."""
    SUCCESS = "success"
    RETRY = "retry"
    FALLBACK = "fallback"
    USER_INTERVENTION = "user_intervention"
    FAILURE = "failure"


class ErrorRecoveryStrategy(ABC):
    """Base class for error recovery strategies."""
    
    def __init__(self, name: str, max_attempts: int = 3):
        self.name = name
        self.max_attempts = max_attempts
        self.attempt_count = 0
    
    @abstractmethod
    async def recover(
        self,
        error: WorkflowPlatformError,
        context: Dict[str, Any],
        original_function: Callable,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Attempt to recover from the error."""
        pass
    
    def can_recover(self, error: WorkflowPlatformError) -> bool:
        """Check if this strategy can recover from the given error."""
        return error.recoverable and self.attempt_count < self.max_attempts
    
    def reset(self):
        """Reset the strategy for reuse."""
        self.attempt_count = 0


class RetryStrategy(ErrorRecoveryStrategy):
    """Strategy that retries the operation with exponential backoff."""
    
    def __init__(
        self,
        name: str = "retry",
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        super().__init__(name, max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    async def recover(
        self,
        error: WorkflowPlatformError,
        context: Dict[str, Any],
        original_function: Callable,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Retry the operation with exponential backoff."""
        if not self.can_recover(error):
            return RecoveryResult.FAILURE, None
        
        self.attempt_count += 1
        
        # Calculate delay
        delay = min(
            self.base_delay * (self.exponential_base ** (self.attempt_count - 1)),
            self.max_delay
        )
        
        # Add jitter to prevent thundering herd
        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)
        
        # Use retry_after from error if available
        if error.retry_after:
            delay = max(delay, error.retry_after)
        
        logger.info(
            f"Retrying operation after {delay:.2f}s (attempt {self.attempt_count}/{self.max_attempts})"
        )
        
        await asyncio.sleep(delay)
        
        try:
            result = await original_function(*args, **kwargs)
            logger.info(f"Retry successful on attempt {self.attempt_count}")
            return RecoveryResult.SUCCESS, result
        except Exception as e:
            logger.warning(f"Retry attempt {self.attempt_count} failed: {e}")
            if self.attempt_count >= self.max_attempts:
                return RecoveryResult.FAILURE, None
            return RecoveryResult.RETRY, None


class FallbackStrategy(ErrorRecoveryStrategy):
    """Strategy that uses fallback operations or values."""
    
    def __init__(
        self,
        name: str = "fallback",
        fallback_function: Optional[Callable] = None,
        fallback_value: Any = None
    ):
        super().__init__(name, max_attempts=1)
        self.fallback_function = fallback_function
        self.fallback_value = fallback_value
    
    async def recover(
        self,
        error: WorkflowPlatformError,
        context: Dict[str, Any],
        original_function: Callable,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Use fallback function or value."""
        if not self.can_recover(error):
            return RecoveryResult.FAILURE, None
        
        self.attempt_count += 1
        
        try:
            if self.fallback_function:
                logger.info(f"Using fallback function for {error.error_code}")
                result = await self.fallback_function(*args, **kwargs)
                return RecoveryResult.SUCCESS, result
            elif self.fallback_value is not None:
                logger.info(f"Using fallback value for {error.error_code}")
                return RecoveryResult.SUCCESS, self.fallback_value
            else:
                logger.warning("No fallback function or value configured")
                return RecoveryResult.FAILURE, None
        except Exception as e:
            logger.error(f"Fallback strategy failed: {e}")
            return RecoveryResult.FAILURE, None


class UserInterventionStrategy(ErrorRecoveryStrategy):
    """Strategy that requires user intervention to resolve the error."""
    
    def __init__(
        self,
        name: str = "user_intervention",
        intervention_message: Optional[str] = None,
        intervention_callback: Optional[Callable] = None
    ):
        super().__init__(name, max_attempts=1)
        self.intervention_message = intervention_message
        self.intervention_callback = intervention_callback
    
    async def recover(
        self,
        error: WorkflowPlatformError,
        context: Dict[str, Any],
        original_function: Callable,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Request user intervention."""
        if not self.can_recover(error):
            return RecoveryResult.FAILURE, None
        
        self.attempt_count += 1
        
        message = self.intervention_message or error.user_message
        
        logger.info(f"Requesting user intervention: {message}")
        
        if self.intervention_callback:
            try:
                await self.intervention_callback(error, context, message)
            except Exception as e:
                logger.error(f"Intervention callback failed: {e}")
        
        return RecoveryResult.USER_INTERVENTION, {
            "message": message,
            "error": error.to_dict(),
            "context": context
        }


class CompositeRecoveryStrategy(ErrorRecoveryStrategy):
    """Strategy that combines multiple recovery strategies."""
    
    def __init__(
        self,
        name: str = "composite",
        strategies: List[ErrorRecoveryStrategy] = None
    ):
        super().__init__(name, max_attempts=1)
        self.strategies = strategies or []
        self.current_strategy_index = 0
    
    def add_strategy(self, strategy: ErrorRecoveryStrategy):
        """Add a recovery strategy to the chain."""
        self.strategies.append(strategy)
    
    async def recover(
        self,
        error: WorkflowPlatformError,
        context: Dict[str, Any],
        original_function: Callable,
        *args,
        **kwargs
    ) -> tuple[RecoveryResult, Any]:
        """Try each strategy in sequence until one succeeds."""
        for i, strategy in enumerate(self.strategies):
            if strategy.can_recover(error):
                logger.info(f"Trying recovery strategy: {strategy.name}")
                
                result, value = await strategy.recover(
                    error, context, original_function, *args, **kwargs
                )
                
                if result == RecoveryResult.SUCCESS:
                    return result, value
                elif result == RecoveryResult.USER_INTERVENTION:
                    return result, value
                elif result == RecoveryResult.RETRY:
                    # Continue with the same strategy
                    continue
                # If FALLBACK or FAILURE, try next strategy
        
        return RecoveryResult.FAILURE, None
    
    def reset(self):
        """Reset all strategies."""
        super().reset()
        for strategy in self.strategies:
            strategy.reset()
        self.current_strategy_index = 0


def create_default_recovery_strategy(error_category: ErrorCategory) -> ErrorRecoveryStrategy:
    """Create a default recovery strategy based on error category."""
    
    if error_category == ErrorCategory.NETWORK:
        return CompositeRecoveryStrategy(
            name="network_recovery",
            strategies=[
                RetryStrategy(max_attempts=3, base_delay=1.0),
                UserInterventionStrategy(
                    intervention_message="Network connection issue. Please check your internet connection."
                )
            ]
        )
    
    elif error_category == ErrorCategory.AUTHENTICATION:
        return UserInterventionStrategy(
            intervention_message="Authentication failed. Please check your credentials and try again."
        )
    
    elif error_category == ErrorCategory.INTEGRATION:
        return CompositeRecoveryStrategy(
            name="integration_recovery",
            strategies=[
                RetryStrategy(max_attempts=2, base_delay=2.0),
                UserInterventionStrategy(
                    intervention_message="External service is temporarily unavailable. Please try again later."
                )
            ]
        )
    
    elif error_category == ErrorCategory.DATABASE:
        return RetryStrategy(max_attempts=3, base_delay=0.5, max_delay=5.0)
    
    elif error_category == ErrorCategory.VALIDATION:
        return UserInterventionStrategy(
            intervention_message="Please correct the input errors and try again."
        )
    
    else:
        return RetryStrategy(max_attempts=2, base_delay=1.0)