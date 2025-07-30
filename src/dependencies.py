"""Dependency injection system for the Natural Language Workflow Platform."""

from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from src.config import settings
from src.services.database import DatabaseService
from src.services.redis_service import RedisService
from src.services.vector_store import VectorStoreService


class WorkflowDependencies:
    """Dependency injection container for workflow agents."""
    
    def __init__(
        self,
        db_service: Optional[DatabaseService] = None,
        vector_store: Optional[VectorStoreService] = None,
        api_clients: Optional[Dict[str, Any]] = None,
        user_context: Optional[Dict[str, Any]] = None,
        redis_service: Optional[RedisService] = None
    ):
        self.db_service = db_service
        self.vector_store = vector_store
        self.api_clients = api_clients or {}
        self.user_context = user_context or {}
        self.redis_service = redis_service
    
    @classmethod
    async def create(
        cls,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> "WorkflowDependencies":
        """Create a new dependency container with initialized connections."""
        
        # Initialize database service
        db_service = await DatabaseService.create()
        
        # Initialize Redis service
        redis_service = await RedisService.create()
        
        # Initialize vector store service
        vector_store = VectorStoreService()
        
        # Initialize API clients (placeholder)
        api_clients = {}  # TODO: Initialize actual API clients
        
        # Set user context
        user_context = {
            "user_id": user_id,
            "session_id": session_id
        }
        
        return cls(
            db_service=db_service,
            vector_store=vector_store,
            api_clients=api_clients,
            user_context=user_context,
            redis_service=redis_service
        )
    
    async def close(self):
        """Close all connections and cleanup resources."""
        if self.db_service:
            await self.db_service.close()
        
        if self.redis_service:
            await self.redis_service.close()
            
        if self.vector_store:
            await self.vector_store.close()


@asynccontextmanager
async def get_dependencies(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
):
    """Context manager for dependency injection."""
    deps = await WorkflowDependencies.create(user_id, session_id)
    try:
        yield deps
    finally:
        await deps.close()