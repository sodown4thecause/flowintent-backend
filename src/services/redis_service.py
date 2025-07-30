"""Redis service for the Natural Language Workflow Platform."""

import json
from typing import Any, Dict, List, Optional, Union
import redis.asyncio as redis
from contextlib import asynccontextmanager

from src.config import settings


class RedisService:
    """Service for Redis operations."""
    
    def __init__(self, client: Optional[redis.Redis] = None):
        """Initialize the Redis service."""
        self.client = client
    
    @classmethod
    async def create(cls) -> "RedisService":
        """Create a new Redis service with connection."""
        try:
            client = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await client.ping()
            return cls(client=client)
        except Exception as e:
            print(f"Error creating Redis client: {e}")
            return cls(client=None)
    
    async def close(self):
        """Close the Redis connection."""
        if self.client:
            await self.client.close()
    
    async def set(
        self, 
        key: str, 
        value: Union[str, Dict, List], 
        expire: Optional[int] = None
    ) -> bool:
        """Set a key-value pair in Redis."""
        if not self.client:
            raise ValueError("Redis client not initialized")
        
        try:
            # Convert dict/list to JSON string
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            
            await self.client.set(key, value)
            
            if expire:
                await self.client.expire(key, expire)
            
            return True
        except Exception as e:
            print(f"Redis set error: {e}")
            return False
    
    async def get(self, key: str, parse_json: bool = True) -> Any:
        """Get a value from Redis."""
        if not self.client:
            raise ValueError("Redis client not initialized")
        
        try:
            value = await self.client.get(key)
            
            if value and parse_json:
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            
            return value
        except Exception as e:
            print(f"Redis get error: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not self.client:
            raise ValueError("Redis client not initialized")
        
        try:
            return bool(await self.client.delete(key))
        except Exception as e:
            print(f"Redis delete error: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        if not self.client:
            raise ValueError("Redis client not initialized")
        
        try:
            return bool(await self.client.exists(key))
        except Exception as e:
            print(f"Redis exists error: {e}")
            return False


@asynccontextmanager
async def get_redis():
    """Context manager for Redis service."""
    redis_service = await RedisService.create()
    try:
        yield redis_service
    finally:
        await redis_service.close()