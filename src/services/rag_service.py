"""RAG (Retrieval-Augmented Generation) service for enhanced AI responses."""

import asyncio
import logging
import json
import re
import time
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime
import uuid
import numpy as np
from pydantic import BaseModel, Field

from src.services.vector_store import VectorStoreService
from src.services.scraping_service import ScrapingService, ScrapingResult
from src.errors import handle_errors

logger = logging.getLogger(__name__)


class Document(BaseModel):
    """A document for RAG processing."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = Field(..., description="Document content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    source: str = Field(..., description="Document source")
    source_id: Optional[str] = Field(None, description="Source identifier")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")
    timestamp: datetime = Field(default_factory=datetime.now)


class RAGQuery(BaseModel):
    """A query for RAG processing."""
    query: str = Field(..., description="User query")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Metadata filters")
    top_k: int = Field(5, description="Number of documents to retrieve")
    rerank: bool = Field(True, description="Whether to rerank results")
    use_hybrid_search: bool = Field(True, description="Whether to use hybrid search")


class RAGResult(BaseModel):
    """Result of RAG processing."""
    query: str = Field(..., description="Original query")
    documents: List[Document] = Field(..., description="Retrieved documents")
    augmented_prompt: str = Field(..., description="Augmented prompt for generation")
    sources: List[Dict[str, Any]] = Field(..., description="Source information")


class RAGService:
    """Service for Retrieval-Augmented Generation."""
    
    def __init__(
        self,
        vector_store: VectorStoreService,
        scraping_service: Optional[ScrapingService] = None
    ):
        self.vector_store = vector_store
        self.scraping_service = scraping_service
        self.collection_name = "rag_documents"
    
    @handle_errors
    async def add_document(self, document: Document) -> bool:
        """Add a document to the RAG system."""
        # Generate embedding if not provided
        if not document.embedding:
            document.embedding = await self._generate_embedding(document.content)
        
        # Store in vector database
        success = await self.vector_store.store(
            id=document.id,
            content={
                "id": document.id,
                "content": document.content,
                "metadata": document.metadata,
                "source": document.source,
                "source_id": document.source_id,
                "timestamp": document.timestamp.isoformat()
            },
            embedding=document.embedding,
            collection_type=self.collection_name
        )
        
        return success
    
    @handle_errors
    async def add_documents(self, documents: List[Document]) -> int:
        """Add multiple documents to the RAG system."""
        success_count = 0
        
        for document in documents:
            if await self.add_document(document):
                success_count += 1
        
        return success_count
    
    @handle_errors
    async def add_text(
        self,
        text: str,
        source: str,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Document:
        """Add text as a document to the RAG system."""
        document = Document(
            content=text,
            source=source,
            source_id=source_id,
            metadata=metadata or {}
        )
        
        await self.add_document(document)
        return document
    
    @handle_errors
    async def add_url(
        self,
        url: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 1000
    ) -> List[Document]:
        """Scrape a URL and add its content as documents."""
        if not self.scraping_service:
            raise ValueError("Scraping service not available")
        
        # Scrape the URL
        scrape_result = await self.scraping_service.scrape_url(url)
        
        if not scrape_result.success:
            logger.warning(f"Failed to scrape URL: {url}, error: {scrape_result.error}")
            return []
        
        # Chunk the content
        chunks = self._chunk_text(scrape_result.content, chunk_size)
        
        # Create documents
        documents = []
        for i, chunk in enumerate(chunks):
            doc_metadata = {
                "url": url,
                "title": scrape_result.title,
                "chunk": i,
                "total_chunks": len(chunks)
            }
            
            if metadata:
                doc_metadata.update(metadata)
            
            document = Document(
                content=chunk,
                source="web",
                source_id=url,
                metadata=doc_metadata
            )
            
            await self.add_document(document)
            documents.append(document)
        
        return documents
    
    @handle_errors
    async def query(self, rag_query: RAGQuery) -> RAGResult:
        """Query the RAG system."""
        # Generate embedding for query
        query_embedding = await self._generate_embedding(rag_query.query)
        
        # Search vector database
        results = await self.vector_store.search(
            query=query_embedding,
            collection_type=self.collection_name,
            limit=rag_query.top_k,
            threshold=0.6
        )
        
        # Convert results to documents
        documents = []
        for result in results:
            content_dict = result.content
            
            # Parse timestamp if it's a string
            timestamp = content_dict.get("timestamp")
            if isinstance(timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(timestamp)
                except:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            
            document = Document(
                id=content_dict.get("id", str(uuid.uuid4())),
                content=content_dict.get("content", ""),
                metadata=content_dict.get("metadata", {}),
                source=content_dict.get("source", "unknown"),
                source_id=content_dict.get("source_id"),
                timestamp=timestamp
            )
            
            documents.append(document)
        
        # Rerank if requested
        if rag_query.rerank and len(documents) > 1:
            documents = await self._rerank_documents(rag_query.query, documents)
        
        # Create augmented prompt
        augmented_prompt = self._create_augmented_prompt(rag_query.query, documents)
        
        # Extract source information
        sources = [
            {
                "id": doc.id,
                "source": doc.source,
                "source_id": doc.source_id,
                "metadata": doc.metadata
            }
            for doc in documents
        ]
        
        return RAGResult(
            query=rag_query.query,
            documents=documents,
            augmented_prompt=augmented_prompt,
            sources=sources
        )
    
    @handle_errors
    async def search_web_and_query(
        self,
        query: str,
        search_urls: List[str],
        top_k: int = 5
    ) -> RAGResult:
        """Search the web for information and then query the RAG system."""
        if not self.scraping_service:
            raise ValueError("Scraping service not available")
        
        # Scrape URLs
        documents = []
        for url in search_urls:
            url_docs = await self.add_url(url)
            documents.extend(url_docs)
        
        # Create RAG query
        rag_query = RAGQuery(
            query=query,
            top_k=top_k
        )
        
        # Query the RAG system
        return await self.query(rag_query)
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        return await self.vector_store.generate_embedding(text)
    
    def _chunk_text(self, text: str, chunk_size: int) -> List[str]:
        """Split text into chunks of approximately equal size."""
        # Simple chunking by character count
        if len(text) <= chunk_size:
            return [text]
        
        # Split by paragraphs first
        paragraphs = text.split("\n\n")
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # If paragraph is too long, split it further
            if len(paragraph) > chunk_size:
                sentences = re.split(r'(?<=[.!?])\s+', paragraph)
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) <= chunk_size:
                        current_chunk += sentence + " "
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
            else:
                # Add paragraph if it fits
                if len(current_chunk) + len(paragraph) <= chunk_size:
                    current_chunk += paragraph + "\n\n"
                else:
                    chunks.append(current_chunk.strip())
                    current_chunk = paragraph + "\n\n"
        
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def _rerank_documents(
        self,
        query: str,
        documents: List[Document]
    ) -> List[Document]:
        """Rerank documents based on relevance to query."""
        # Simple reranking based on keyword matching
        # In a production system, this would use a more sophisticated reranking model
        
        query_terms = set(query.lower().split())
        scores = []
        
        for doc in documents:
            content = doc.content.lower()
            
            # Count term frequency
            term_count = sum(1 for term in query_terms if term in content)
            
            # Calculate density (terms per length)
            density = term_count / (len(content) + 1)
            
            # Calculate position score (earlier mentions are better)
            position_score = 0
            for term in query_terms:
                pos = content.find(term)
                if pos >= 0:
                    position_score += 1 - (pos / len(content))
            
            # Combined score
            score = term_count * 0.5 + density * 0.3 + position_score * 0.2
            scores.append(score)
        
        # Sort documents by score
        sorted_docs = [doc for _, doc in sorted(
            zip(scores, documents),
            key=lambda pair: pair[0],
            reverse=True
        )]
        
        return sorted_docs
    
    def _create_augmented_prompt(self, query: str, documents: List[Document]) -> str:
        """Create an augmented prompt with retrieved documents."""
        context_parts = []
        
        for i, doc in enumerate(documents):
            context_parts.append(f"[Document {i+1}] {doc.content}")
        
        context = "\n\n".join(context_parts)
        
        augmented_prompt = f"""
Answer the following query based on the provided context. If the context doesn't contain relevant information, say so.

Context:
{context}

Query: {query}

Answer:
"""
        
        return augmented_prompt.strip()


# Factory function for RAG service
async def get_rag_service(
    vector_store: VectorStoreService,
    scraping_service: Optional[ScrapingService] = None
) -> RAGService:
    """Get RAG service instance."""
    return RAGService(vector_store, scraping_service)