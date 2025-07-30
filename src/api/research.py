"""API endpoints for research, scraping, and RAG capabilities."""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field, HttpUrl

from src.agents.research_agent import (
    research_agent,
    ResearchAgentDeps,
    ResearchTask,
    WebScrapingTask,
    RAGTask,
    research_topic,
    scrape_and_analyze
)
from src.services.research_service import get_research_service, ResearchQuery
from src.services.scraping_service import scraping_service, ScrapingConfig
from src.services.rag_service import get_rag_service, RAGDocument
from src.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    """Request for conducting research."""
    query: str = Field(..., description="Research query or topic")
    depth: str = Field("medium", description="Research depth: shallow, medium, deep")
    sources: List[str] = Field(default_factory=list, description="Specific sources to include")
    time_range: Optional[str] = Field(None, description="Time range: 1d, 1w, 1m, 1y")
    include_academic: bool = Field(False, description="Include academic sources")
    include_news: bool = Field(True, description="Include news sources")
    max_sources: int = Field(10, ge=1, le=50, description="Maximum number of sources")


class ScrapingRequest(BaseModel):
    """Request for web scraping."""
    urls: List[HttpUrl] = Field(..., description="URLs to scrape")
    extract_links: bool = Field(True, description="Extract links from pages")
    extract_images: bool = Field(False, description="Extract images from pages")
    javascript_enabled: bool = Field(False, description="Enable JavaScript rendering")
    wait_for_selector: Optional[str] = Field(None, description="CSS selector to wait for")
    custom_headers: Dict[str, str] = Field(default_factory=dict, description="Custom HTTP headers")


class RAGQueryRequest(BaseModel):
    """Request for RAG query."""
    query: str = Field(..., description="Query for RAG system")
    context: Optional[str] = Field(None, description="Additional context")
    collection: str = Field("documents", description="Document collection to search")
    max_results: int = Field(5, ge=1, le=20, description="Maximum number of results")
    include_sources: bool = Field(True, description="Include source documents in response")


class RAGDocumentRequest(BaseModel):
    """Request to add documents to RAG system."""
    documents: List[Dict[str, Any]] = Field(..., description="Documents to add")
    collection: str = Field("documents", description="Collection to add documents to")


class WorkflowResearchRequest(BaseModel):
    """Request to create a research workflow."""
    topic: str = Field(..., description="Research topic")
    workflow_name: Optional[str] = Field(None, description="Custom workflow name")
    depth: str = Field("deep", description="Research depth")
    include_academic: bool = Field(True, description="Include academic sources")
    include_news: bool = Field(True, description="Include news sources")


@router.post("/conduct")
async def conduct_research(
    request: ResearchRequest,
    current_user: User = Depends(get_current_user),
    research_service = Depends(get_research_service)
):
    """Conduct comprehensive research on a topic."""
    try:
        # Create research query
        research_query = ResearchQuery(
            query=request.query,
            depth=request.depth,
            sources=request.sources,
            time_range=request.time_range,
            include_academic=request.include_academic,
            include_news=request.include_news,
            max_sources=request.max_sources
        )
        
        # Conduct research
        result = await research_service.conduct_research(research_query)
        
        # Convert to serializable format
        return {
            "query": result.query,
            "summary": result.summary,
            "key_findings": result.key_findings,
            "sources": [
                {
                    "url": source.url,
                    "title": source.title,
                    "content": source.content[:500],  # Limit content
                    "relevance_score": source.relevance_score,
                    "credibility_score": source.credibility_score,
                    "source_type": source.source_type,
                    "timestamp": source.timestamp.isoformat() if source.timestamp else None
                }
                for source in result.sources
            ],
            "confidence_score": result.confidence_score,
            "research_depth": result.research_depth,
            "timestamp": result.timestamp.isoformat(),
            "follow_up_questions": result.follow_up_questions,
            "related_topics": result.related_topics
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")


@router.post("/scrape")
async def scrape_websites(
    request: ScrapingRequest,
    current_user: User = Depends(get_current_user)
):
    """Scrape multiple websites and extract structured data."""
    try:
        # Configure scraping
        config = ScrapingConfig(
            extract_links=request.extract_links,
            extract_images=request.extract_images,
            javascript_enabled=request.javascript_enabled,
            wait_for_selector=request.wait_for_selector,
            custom_headers=request.custom_headers,
            extract_structured_data=True
        )
        
        # Convert URLs to strings
        urls = [str(url) for url in request.urls]
        
        # Scrape URLs
        results = await scraping_service.scrape_multiple(
            urls=urls,
            config=config,
            max_concurrent=3
        )
        
        # Convert to serializable format
        scraped_data = []
        for result in results:
            scraped_data.append({
                "url": result.url,
                "title": result.title,
                "content": result.content[:2000],  # Limit content length
                "links": result.links[:20] if result.links else [],
                "images": result.images[:10] if result.images else [],
                "metadata": result.metadata,
                "structured_data": result.structured_data,
                "status_code": result.status_code,
                "response_time": result.response_time,
                "timestamp": result.timestamp.isoformat()
            })
        
        return {
            "scraped_count": len(scraped_data),
            "results": scraped_data
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Web scraping failed: {str(e)}")


@router.post("/rag/query")
async def query_rag(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """Query the RAG system for enhanced AI responses."""
    try:
        if request.include_sources:
            # Get response with sources
            result = await rag_service.query_with_sources(
                query=request.query,
                context=request.context,
                collection=request.collection,
                max_results=request.max_results
            )
            
            return {
                "response": result.response,
                "sources": [
                    {
                        "id": source.id,
                        "content": source.content[:500],  # Limit content
                        "metadata": source.metadata,
                        "timestamp": source.timestamp.isoformat()
                    }
                    for source in result.sources
                ],
                "confidence_score": result.confidence_score,
                "processing_time": result.processing_time,
                "metadata": result.metadata
            }
        else:
            # Get simple response
            response = await rag_service.query(
                query=request.query,
                context=request.context,
                collection=request.collection,
                max_results=request.max_results
            )
            
            return {
                "response": response,
                "sources": [],
                "confidence_score": None,
                "processing_time": 0.0
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@router.post("/rag/documents")
async def add_rag_documents(
    request: RAGDocumentRequest,
    current_user: User = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """Add documents to the RAG system."""
    try:
        # Convert to RAGDocument objects
        rag_documents = []
        for i, doc_data in enumerate(request.documents):
            doc = RAGDocument(
                id=doc_data.get("id", f"doc_{current_user.id}_{i}_{int(datetime.now().timestamp())}"),
                content=doc_data.get("content", ""),
                metadata=doc_data.get("metadata", {})
            )
            rag_documents.append(doc)
        
        # Add documents in batch
        added_count = await rag_service.add_documents_batch(
            documents=rag_documents,
            collection=request.collection
        )
        
        return {
            "added_count": added_count,
            "total_requested": len(request.documents),
            "collection": request.collection
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add documents: {str(e)}")


@router.get("/rag/documents/{collection}")
async def list_rag_documents(
    collection: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """List documents in a RAG collection."""
    try:
        documents = await rag_service.list_documents(collection, limit)
        
        return {
            "collection": collection,
            "count": len(documents),
            "documents": [
                {
                    "id": doc.id,
                    "content": doc.content[:200],  # Preview
                    "metadata": doc.metadata,
                    "timestamp": doc.timestamp.isoformat()
                }
                for doc in documents
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.delete("/rag/documents/{collection}/{document_id}")
async def delete_rag_document(
    collection: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    rag_service = Depends(get_rag_service)
):
    """Delete a document from the RAG system."""
    try:
        success = await rag_service.delete_document(document_id, collection)
        
        if success:
            return {"message": f"Document {document_id} deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Document not found")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")


@router.post("/workflow/create")
async def create_research_workflow(
    request: WorkflowResearchRequest,
    current_user: User = Depends(get_current_user),
    research_service = Depends(get_research_service),
    rag_service = Depends(get_rag_service)
):
    """Create an automated research workflow."""
    try:
        # Create agent dependencies
        deps = ResearchAgentDeps(
            research_service=research_service,
            scraping_service=scraping_service,
            rag_service=rag_service,
            user_id=str(current_user.id)
        )
        
        # Create research workflow
        workflow = await research_agent.run_tool(
            "create_research_workflow",
            deps=deps,
            research_topic=request.topic,
            workflow_name=request.workflow_name
        )
        
        return {
            "workflow_id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "steps": [
                {
                    "id": step.id,
                    "name": step.name,
                    "type": step.type,
                    "service": step.service
                }
                for step in workflow.steps
            ],
            "estimated_runtime": workflow.estimated_runtime
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.post("/analyze")
async def analyze_research_data(
    data: List[Dict[str, Any]],
    analysis_type: str = "summary",
    current_user: User = Depends(get_current_user),
    research_service = Depends(get_research_service),
    rag_service = Depends(get_rag_service)
):
    """Analyze research data and provide insights."""
    try:
        # Create agent dependencies
        deps = ResearchAgentDeps(
            research_service=research_service,
            scraping_service=scraping_service,
            rag_service=rag_service,
            user_id=str(current_user.id)
        )
        
        # Analyze data
        analysis = await research_agent.run_tool(
            "analyze_research_data",
            deps=deps,
            data=data,
            analysis_type=analysis_type
        )
        
        return analysis
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/quick/{topic}")
async def quick_research(
    topic: str,
    depth: str = "medium",
    current_user: User = Depends(get_current_user)
):
    """Quick research on a topic (simplified endpoint)."""
    try:
        result = await research_topic(
            topic=topic,
            depth=depth,
            user_id=str(current_user.id)
        )
        
        return {
            "topic": topic,
            "result": result.result,
            "sources": result.sources,
            "confidence_score": result.confidence_score,
            "processing_time": result.processing_time
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick research failed: {str(e)}")


@router.post("/scrape-analyze")
async def scrape_and_analyze_endpoint(
    urls: List[HttpUrl],
    current_user: User = Depends(get_current_user)
):
    """Scrape URLs and analyze the content (simplified endpoint)."""
    try:
        url_strings = [str(url) for url in urls]
        
        result = await scrape_and_analyze(
            urls=url_strings,
            user_id=str(current_user.id)
        )
        
        return {
            "urls_processed": len(url_strings),
            "result": result.result,
            "sources": result.sources,
            "processing_time": result.processing_time
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape and analyze failed: {str(e)}")


# Background task endpoints
@router.post("/background/research")
async def background_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Start background research task."""
    task_id = f"research_{current_user.id}_{int(datetime.now().timestamp())}"
    
    async def research_task():
        try:
            # This would store results in a task queue/database
            result = await research_topic(
                topic=request.query,
                depth=request.depth,
                user_id=str(current_user.id)
            )
            # Store result for later retrieval
            print(f"Background research completed: {task_id}")
        except Exception as e:
            print(f"Background research failed: {task_id}, error: {e}")
    
    background_tasks.add_task(research_task)
    
    return {
        "task_id": task_id,
        "status": "started",
        "message": "Research task started in background"
    }