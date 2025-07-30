"""API endpoints for workflow recommendations using ChromaDB."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from ..services.vector_store import VectorStoreService, get_vector_store
from ..dependencies import get_current_user
from ..models.user import User
from ..models.workflow import ExecutableWorkflow


router = APIRouter(prefix="/workflow-recommendations", tags=["workflow-recommendations"])


class WorkflowRecommendation(BaseModel):
    """Model for workflow recommendation."""
    id: str
    name: str
    description: str
    similarity_score: float
    steps_count: int
    estimated_runtime: int


class SimilarWorkflowsResponse(BaseModel):
    """Response model for similar workflows."""
    query: str
    recommendations: List[WorkflowRecommendation]


class StoreWorkflowRequest(BaseModel):
    """Request model for storing workflow in vector store."""
    workflow: ExecutableWorkflow
    tags: List[str] = []
    category: Optional[str] = None


@router.get("/similar", response_model=SimilarWorkflowsResponse)
async def find_similar_workflows(
    query: str = Query(..., description="Natural language description of the workflow"),
    limit: int = Query(5, description="Maximum number of recommendations to return"),
    threshold: float = Query(0.7, description="Minimum similarity score threshold"),
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Find similar workflows based on natural language description."""
    try:
        # Search for similar workflows in ChromaDB
        results = await vector_store.search(
            query=query,
            collection_type="workflows",
            limit=limit,
            threshold=threshold
        )
        
        # Convert results to recommendation model
        recommendations = []
        for result in results:
            workflow_data = result.content
            
            # Extract workflow details
            recommendation = WorkflowRecommendation(
                id=workflow_data.get("id", "unknown"),
                name=workflow_data.get("name", "Unnamed Workflow"),
                description=workflow_data.get("description", ""),
                similarity_score=result.score,
                steps_count=len(workflow_data.get("steps", [])),
                estimated_runtime=workflow_data.get("estimated_runtime", 60)
            )
            
            recommendations.append(recommendation)
        
        return SimilarWorkflowsResponse(
            query=query,
            recommendations=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to find similar workflows: {str(e)}")


@router.post("/store", response_model=Dict[str, Any])
async def store_workflow_in_vector_db(
    request: StoreWorkflowRequest,
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Store a workflow in the vector database for future recommendations."""
    try:
        # Prepare workflow content with additional metadata
        workflow_content = request.workflow.dict()
        workflow_content["tags"] = request.tags
        workflow_content["category"] = request.category
        workflow_content["user_id"] = str(current_user.id)
        
        # Generate text for embedding
        text_for_embedding = f"{request.workflow.name} {request.workflow.description}"
        if request.tags:
            text_for_embedding += f" {' '.join(request.tags)}"
        if request.category:
            text_for_embedding += f" {request.category}"
        
        # Generate embedding
        embedding = await vector_store.generate_embedding(text_for_embedding)
        
        # Store in vector database
        success = await vector_store.store(
            id=request.workflow.id,
            content=workflow_content,
            embedding=embedding,
            collection_type="workflows"
        )
        
        if success:
            return {
                "success": True,
                "message": f"Workflow '{request.workflow.name}' stored successfully",
                "workflow_id": request.workflow.id
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to store workflow in vector database")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store workflow: {str(e)}")


@router.get("/popular", response_model=List[WorkflowRecommendation])
async def get_popular_workflows(
    category: Optional[str] = None,
    limit: int = Query(10, description="Maximum number of workflows to return"),
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Get popular workflow templates."""
    try:
        # List items from vector database
        items = await vector_store.list_items(
            collection_type="workflows",
            limit=limit
        )
        
        # Filter by category if specified
        if category:
            items = [item for item in items if item["content"].get("category") == category]
        
        # Convert to recommendation model
        recommendations = []
        for item in items[:limit]:
            workflow_data = item["content"]
            
            recommendation = WorkflowRecommendation(
                id=item["id"],
                name=workflow_data.get("name", "Unnamed Workflow"),
                description=workflow_data.get("description", ""),
                similarity_score=1.0,  # Not based on similarity
                steps_count=len(workflow_data.get("steps", [])),
                estimated_runtime=workflow_data.get("estimated_runtime", 60)
            )
            
            recommendations.append(recommendation)
        
        return recommendations
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get popular workflows: {str(e)}")


@router.post("/seed-templates")
async def seed_workflow_templates(
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Seed the vector database with example workflow templates."""
    try:
        # Only allow admin users to seed templates
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Only admin users can seed templates")
        
        # Example workflow templates
        templates = [
            {
                "id": "template-data-processing",
                "name": "Data Processing Pipeline",
                "description": "Extract, transform, and load data from various sources",
                "category": "data",
                "tags": ["data", "etl", "processing"],
                "steps": [
                    {
                        "id": "extract",
                        "name": "Extract Data",
                        "type": "trigger",
                        "service": "data_source",
                        "configuration": {"source_type": "api"}
                    },
                    {
                        "id": "transform",
                        "name": "Transform Data",
                        "type": "transform",
                        "service": "transformer",
                        "configuration": {},
                        "dependencies": ["extract"]
                    },
                    {
                        "id": "load",
                        "name": "Load Data",
                        "type": "action",
                        "service": "data_sink",
                        "configuration": {"destination": "database"},
                        "dependencies": ["transform"]
                    }
                ],
                "estimated_runtime": 300
            },
            {
                "id": "template-notification",
                "name": "Smart Notification System",
                "description": "Monitor events and send intelligent notifications",
                "category": "automation",
                "tags": ["notification", "alerts", "monitoring"],
                "steps": [
                    {
                        "id": "monitor",
                        "name": "Monitor Events",
                        "type": "trigger",
                        "service": "event_monitor",
                        "configuration": {"interval": 300}
                    },
                    {
                        "id": "analyze",
                        "name": "Analyze Event",
                        "type": "condition",
                        "service": "analyzer",
                        "configuration": {},
                        "dependencies": ["monitor"]
                    },
                    {
                        "id": "notify",
                        "name": "Send Notification",
                        "type": "action",
                        "service": "notifier",
                        "configuration": {"channels": ["email"]},
                        "dependencies": ["analyze"]
                    }
                ],
                "estimated_runtime": 60
            },
            {
                "id": "template-content-generation",
                "name": "AI Content Generation",
                "description": "Generate content using AI based on prompts and templates",
                "category": "ai",
                "tags": ["content", "ai", "generation"],
                "steps": [
                    {
                        "id": "input",
                        "name": "Content Input",
                        "type": "trigger",
                        "service": "user_input",
                        "configuration": {"input_type": "form"}
                    },
                    {
                        "id": "generate",
                        "name": "Generate Content",
                        "type": "action",
                        "service": "ai_generator",
                        "configuration": {"model": "gpt-4o"},
                        "dependencies": ["input"]
                    },
                    {
                        "id": "review",
                        "name": "Review Content",
                        "type": "condition",
                        "service": "content_reviewer",
                        "configuration": {},
                        "dependencies": ["generate"]
                    },
                    {
                        "id": "publish",
                        "name": "Publish Content",
                        "type": "action",
                        "service": "publisher",
                        "configuration": {"platforms": ["blog"]},
                        "dependencies": ["review"]
                    }
                ],
                "estimated_runtime": 120
            },
            {
                "id": "template-social-media",
                "name": "Social Media Scheduler",
                "description": "Schedule and publish content across social media platforms",
                "category": "marketing",
                "tags": ["social", "marketing", "scheduling"],
                "steps": [
                    {
                        "id": "content",
                        "name": "Content Creation",
                        "type": "trigger",
                        "service": "content_creator",
                        "configuration": {}
                    },
                    {
                        "id": "schedule",
                        "name": "Schedule Posts",
                        "type": "action",
                        "service": "scheduler",
                        "configuration": {"platforms": ["twitter", "linkedin"]},
                        "dependencies": ["content"]
                    },
                    {
                        "id": "analytics",
                        "name": "Track Analytics",
                        "type": "action",
                        "service": "analytics",
                        "configuration": {},
                        "dependencies": ["schedule"]
                    }
                ],
                "estimated_runtime": 90
            },
            {
                "id": "template-customer-support",
                "name": "AI Customer Support",
                "description": "Automate customer support with AI-powered responses",
                "category": "customer-service",
                "tags": ["support", "ai", "automation"],
                "steps": [
                    {
                        "id": "receive",
                        "name": "Receive Inquiry",
                        "type": "trigger",
                        "service": "inquiry_receiver",
                        "configuration": {"sources": ["email", "chat"]}
                    },
                    {
                        "id": "categorize",
                        "name": "Categorize Inquiry",
                        "type": "transform",
                        "service": "categorizer",
                        "configuration": {},
                        "dependencies": ["receive"]
                    },
                    {
                        "id": "generate",
                        "name": "Generate Response",
                        "type": "action",
                        "service": "response_generator",
                        "configuration": {"model": "gpt-4o"},
                        "dependencies": ["categorize"]
                    },
                    {
                        "id": "review",
                        "name": "Human Review",
                        "type": "condition",
                        "service": "human_reviewer",
                        "configuration": {"confidence_threshold": 0.8},
                        "dependencies": ["generate"]
                    },
                    {
                        "id": "send",
                        "name": "Send Response",
                        "type": "action",
                        "service": "response_sender",
                        "configuration": {},
                        "dependencies": ["review"]
                    }
                ],
                "estimated_runtime": 180
            }
        ]
        
        # Store templates in vector database
        stored_count = 0
        for template in templates:
            # Generate text for embedding
            text_for_embedding = f"{template['name']} {template['description']}"
            if template.get("tags"):
                text_for_embedding += f" {' '.join(template['tags'])}"
            if template.get("category"):
                text_for_embedding += f" {template['category']}"
            
            # Generate embedding
            embedding = await vector_store.generate_embedding(text_for_embedding)
            
            # Store in vector database
            success = await vector_store.store(
                id=template["id"],
                content=template,
                embedding=embedding,
                collection_type="workflows"
            )
            
            if success:
                stored_count += 1
        
        return {
            "success": True,
            "message": f"Seeded {stored_count} workflow templates",
            "total_templates": len(templates)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to seed workflow templates: {str(e)}")


@router.get("/search-by-text", response_model=SimilarWorkflowsResponse)
async def search_workflows_by_text(
    text: str = Query(..., description="Text to search for in workflow descriptions"),
    limit: int = Query(5, description="Maximum number of results to return"),
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Search for workflows by text description."""
    try:
        # Search for workflows in ChromaDB
        results = await vector_store.search(
            query=text,
            collection_type="workflows",
            limit=limit,
            threshold=0.5  # Lower threshold for text search
        )
        
        # Convert results to recommendation model
        recommendations = []
        for result in results:
            workflow_data = result.content
            
            recommendation = WorkflowRecommendation(
                id=workflow_data.get("id", "unknown"),
                name=workflow_data.get("name", "Unnamed Workflow"),
                description=workflow_data.get("description", ""),
                similarity_score=result.score,
                steps_count=len(workflow_data.get("steps", [])),
                estimated_runtime=workflow_data.get("estimated_runtime", 60)
            )
            
            recommendations.append(recommendation)
        
        return SimilarWorkflowsResponse(
            query=text,
            recommendations=recommendations
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search workflows: {str(e)}")