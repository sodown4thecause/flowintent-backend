"""Database service for the Natural Language Workflow Platform."""

import asyncpg
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from src.config import settings


class DatabaseService:
    """Service for database operations."""
    
    def __init__(self, pool: Optional[asyncpg.Pool] = None):
        """Initialize the database service."""
        self.pool = pool
    
    @classmethod
    async def create(cls) -> "DatabaseService":
        """Create a new database service with connection pool."""
        try:
            pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=5,
                max_size=20
            )
            return cls(pool=pool)
        except Exception as e:
            print(f"Error creating database pool: {e}")
            return cls(pool=None)
    
    async def close(self):
        """Close the database connection pool."""
        if self.pool:
            await self.pool.close()
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query and return the status."""
        if not self.pool:
            raise ValueError("Database pool not initialized")
        
        try:
            status = await self.pool.execute(query, *args)
            return status
        except Exception as e:
            print(f"Database execution error: {e}")
            raise
    
    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """Execute a query and return all results."""
        if not self.pool:
            raise ValueError("Database pool not initialized")
        
        try:
            rows = await self.pool.fetch(query, *args)
            return [dict(row) for row in rows]
        except Exception as e:
            print(f"Database fetch error: {e}")
            raise
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """Execute a query and return the first result."""
        if not self.pool:
            raise ValueError("Database pool not initialized")
        
        try:
            row = await self.pool.fetchrow(query, *args)
            return dict(row) if row else None
        except Exception as e:
            print(f"Database fetchrow error: {e}")
            raise
    
    async def fetchval(self, query: str, *args) -> Any:
        """Execute a query and return a single value."""
        if not self.pool:
            raise ValueError("Database pool not initialized")
        
        try:
            return await self.pool.fetchval(query, *args)
        except Exception as e:
            print(f"Database fetchval error: {e}")
            raise


@asynccontextmanager
async def get_db():
    """Context manager for database service."""
    db = await DatabaseService.create()
    try:
        yield db
    finally:
        await db.close()