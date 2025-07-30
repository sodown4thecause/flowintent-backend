"""Vector store service for the Natural Language Workflow Platform using ChromaDB."""

from typing import List, Dict, Any, Optional, Union
from contextlib import asynccontextmanager
import httpx
import json
import numpy as np
import logging
import asyncio
from functools import wraps
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.api.models.Collection import Collection

from src.config import settings

logger = logging.getLogger(__name__)


class VectorStoreResult:
    """Result from vector store search."""
    
    def __init__(self, content: Dict[str, Any], score: float):
        """Initialize the vector store result."""
        self.content = content
        self.score = score


def to_async(func):
    """Convert a synchronous function to asynchronous."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper


class VectorStoreService:
    """Service for vector database operations using ChromaDB."""
    
    def __init__(self):
        """Initialize the ChromaDB vector store service."""
        self.client = None
        self.collections = {}
        self.initialized = False
        
        # ChromaDB Cloud credentials
        self.api_key = 'ck-6X1CZXCLGda7QLufJ2nFzjVFm2bpLVrPnSc8hXBC2Rxc'
        self.tenant = '8cfbb0d2-82b9-4250-8054-549cbdefff3f'
        self.database = 'flowimpact'
        
        # Default collection names
        self.default_collections = {
            "workflows": "workflow_templates",
            "intents": "workflow_intents",
            "steps": "workflow_steps",
            "executions": "workflow_executions"
        }
    
    async def initialize(self):
        """Initialize ChromaDB client and collections."""
        if self.initialized:
            return
        
        try:
            # Initialize ChromaDB client
            self.client = await asyncio.to_thread(
                chromadb.CloudClient,
                api_key=self.api_key,
                tenant=self.tenant,
                database=self.database
            )
            
            # Initialize collections
            for key, name in self.default_collections.items():
                try:
                    # Try to get existing collection
                    collection = await asyncio.to_thread(
                        self.client.get_collection,
                        name=name
                    )
                    self.collections[key] = collection
                    logger.info(f"Connected to existing collection: {name}")
                except Exception:
                    # Create collection if it doesn't exist
                    collection = await asyncio.to_thread(
                        self.client.create_collection,
                        name=name,
                        metadata={"description": f"Collection for {key}"}
                    )
                    self.collections[key] = collection
                    logger.info(f"Created new collection: {name}")
            
            self.initialized = True
            logger.info("ChromaDB initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise
    
    async def close(self):
        """Close the ChromaDB client."""
        # ChromaDB client doesn't need explicit closing
        self.client = None
        self.collections = {}
        self.initialized = False
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI API."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "input": text,
                        "model": settings.openai_embedding_model
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Error generating embedding: {response.text}")
                    # Return empty embedding as fallback
                    return [0.0] * 1536
                
                data = response.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            # Return empty embedding as fallback
            return [0.0] * 1536
    
    async def get_collection(self, collection_type: str) -> Collection:
        """Get a collection by type."""
        if not self.initialized:
            await self.initialize()
        
        if collection_type not in self.collections:
            raise ValueError(f"Unknown collection type: {collection_type}")
        
        return self.collections[collection_type]
    
    async def store(
        self, 
        id: str, 
        content: Dict[str, Any], 
        embedding: Optional[List[float]] = None,
        collection_type: str = "workflows"
    ) -> bool:
        """Store content with embedding in ChromaDB."""
        try:
            if not self.initialized:
                await self.initialize()
            
            collection = await self.get_collection(collection_type)
            
            # Convert content to string for storage
            content_str = json.dumps(content)
            
            # Generate embedding if not provided
            if embedding is None:
                # Use the description or name field for embedding generation
                text_for_embedding = content.get("description", content.get("name", content_str))
                embedding = await self.generate_embedding(text_for_embedding)
            
            # Store in ChromaDB
            await asyncio.to_thread(
                collection.add,
                ids=[id],
                embeddings=[embedding],
                metadatas=[content],
                documents=[content_str]
            )
            
            logger.info(f"Stored item {id} in collection {collection_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing in ChromaDB: {e}")
            return False
    
    async def search(
        self, 
        query: Union[str, List[float]],
        collection_type: str = "workflows",
        limit: int = 5,
        threshold: float = 0.7
    ) -> List[VectorStoreResult]:
        """Search for similar items in ChromaDB."""
        try:
            if not self.initialized:
                await self.initialize()
            
            collection = await self.get_collection(collection_type)
            
            # Generate embedding if query is a string
            embedding = query if isinstance(query, list) else await self.generate_embedding(query)
            
            # Search in ChromaDB
            results = await asyncio.to_thread(
                collection.query,
                query_embeddings=[embedding],
                n_results=limit,
                include=["metadatas", "documents", "distances"]
            )
            
            # Process results
            items = []
            if results and results["ids"] and len(results["ids"][0]) > 0:
                for i in range(len(results["ids"][0])):
                    # Convert distance to similarity score (ChromaDB returns distance, not similarity)
                    # Distance is between 0 and 2, where 0 is identical
                    distance = results["distances"][0][i]
                    similarity = 1.0 - (distance / 2.0)
                    
                    if similarity >= threshold:
                        # Use metadata if available, otherwise parse from document
                        if results["metadatas"] and results["metadatas"][0]:
                            content = results["metadatas"][0][i]
                        else:
                            content = json.loads(results["documents"][0][i])
                        
                        items.append(VectorStoreResult(
                            content=content,
                            score=similarity
                        ))
            
            return items
            
        except Exception as e:
            logger.error(f"Error searching in ChromaDB: {e}")
            return []
    
    async def delete(self, id: str, collection_type: str = "workflows") -> bool:
        """Delete an item from ChromaDB."""
        try:
            if not self.initialized:
                await self.initialize()
            
            collection = await self.get_collection(collection_type)
            
            # Delete from ChromaDB
            await asyncio.to_thread(
                collection.delete,
                ids=[id]
            )
            
            logger.info(f"Deleted item {id} from collection {collection_type}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting from ChromaDB: {e}")
            return False
    
    async def get_by_id(self, id: str, collection_type: str = "workflows") -> Optional[Dict[str, Any]]:
        """Get an item by ID from ChromaDB."""
        try:
            if not self.initialized:
                await self.initialize()
            
            collection = await self.get_collection(collection_type)
            
            # Get from ChromaDB
            result = await asyncio.to_thread(
                collection.get,
                ids=[id],
                include=["metadatas", "documents"]
            )
            
            if result and result["ids"] and len(result["ids"]) > 0:
                # Use metadata if available, otherwise parse from document
                if result["metadatas"] and len(result["metadatas"]) > 0:
                    return result["metadatas"][0]
                elif result["documents"] and len(result["documents"]) > 0:
                    return json.loads(result["documents"][0])
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting item from ChromaDB: {e}")
            return None
    
    async def list_items(self, collection_type: str = "workflows", limit: int = 100) -> List[Dict[str, Any]]:
        """List items from a collection."""
        try:
            if not self.initialized:
                await self.initialize()
            
            collection = await self.get_collection(collection_type)
            
            # Get all items from ChromaDB
            result = await asyncio.to_thread(
                collection.get,
                limit=limit,
                include=["metadatas", "documents", "embeddings"]
            )
            
            items = []
            if result and result["ids"] and len(result["ids"]) > 0:
                for i in range(len(result["ids"])):
                    # Use metadata if available, otherwise parse from document
                    if result["metadatas"] and len(result["metadatas"]) > 0:
                        content = result["metadatas"][i]
                    else:
                        content = json.loads(result["documents"][i])
                    
                    items.append({
                        "id": result["ids"][i],
                        "content": content
                    })
            
            return items
            
        except Exception as e:
            logger.error(f"Error listing items from ChromaDB: {e}")
            return []


@asynccontextmanager
async def get_vector_store():
    """Context manager for vector store service."""
    vector_store = VectorStoreService()
    try:
        yield vector_store
    finally:
        await vector_store.close()