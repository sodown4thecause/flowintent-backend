"""API endpoints for community and workflow sharing features."""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from src.models.community import (
    WorkflowTemplate,
    TemplateRating,
    TemplateSearchQuery,
    TemplateSearchResult,
    TemplateAdaptationRequest,
    TemplateAdaptationResult,
    CommunityStats,
    TemplateVisibility,
    TemplateCategory,
    TemplateStatus
)
from src.services.community_service import CommunityService
from src.services.database import DatabaseService, get_db
from src.services.vector_store import VectorStoreService, get_vector_store
from src.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/community", tags=["community"])


class TemplateCreateRequest(BaseModel):
    """Request to create a workflow template."""
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    template_data: Dict[str, Any] = Field(...)
    category: TemplateCategory = Field(...)
    tags: List[str] = Field(default_factory=list)
    visibility: TemplateVisibility = Field(default=TemplateVisibility.PRIVATE)
    required_integrations: List[str] = Field(default_factory=list)
    complexity_level: str = Field(default="medium")


class TemplateUpdateRequest(BaseModel):
    """Request to update a workflow template."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1, max_length=1000)
    category: Optional[TemplateCategory] = None
    tags: Optional[List[str]] = None
    visibility: Optional[TemplateVisibility] = None
    status: Optional[TemplateStatus] = None
    complexity_level: Optional[str] = None


class TemplateRatingRequest(BaseModel):
    """Request to rate a template."""
    rating: int = Field(..., ge=1, le=5)
    review: Optional[str] = Field(None, max_length=1000)


async def get_community_service(
    db: DatabaseService = Depends(get_db),
    vector_store: VectorStoreService = Depends(get_vector_store)
) -> CommunityService:
    """Get community service instance."""
    return CommunityService(db, vector_store)


@router.post("/templates", response_model=WorkflowTemplate)
async def create_template(
    request: TemplateCreateRequest,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Create a new workflow template."""
    try:
        template = WorkflowTemplate(
            name=request.name,
            description=request.description,
            template_data=request.template_data,
            category=request.category,
            tags=request.tags,
            visibility=request.visibility,
            required_integrations=request.required_integrations,
            complexity_level=request.complexity_level,
            created_by=str(current_user.id)
        )
        
        created_template = await community_service.create_template(template, str(current_user.id))
        return created_template
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create template: {str(e)}")


@router.get("/templates/{template_id}", response_model=WorkflowTemplate)
async def get_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Get a workflow template by ID."""
    try:
        template = await community_service.get_template(template_id, str(current_user.id))
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        return template
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")


@router.put("/templates/{template_id}", response_model=WorkflowTemplate)
async def update_template(
    template_id: str,
    request: TemplateUpdateRequest,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Update a workflow template."""
    try:
        # Convert request to dict, excluding None values
        updates = {k: v for k, v in request.dict().items() if v is not None}
        
        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")
        
        updated_template = await community_service.update_template(
            template_id, updates, str(current_user.id)
        )
        
        if not updated_template:
            raise HTTPException(status_code=404, detail="Template not found or access denied")
        
        return updated_template
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update template: {str(e)}")


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Delete a workflow template."""
    try:
        success = await community_service.delete_template(template_id, str(current_user.id))
        
        if not success:
            raise HTTPException(status_code=404, detail="Template not found or access denied")
        
        return {"message": "Template deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete template: {str(e)}")


@router.get("/templates", response_model=TemplateSearchResult)
async def search_templates(
    query: Optional[str] = Query(None, description="Search query"),
    category: Optional[TemplateCategory] = Query(None, description="Filter by category"),
    tags: Optional[str] = Query(None, description="Filter by tags (comma-separated)"),
    required_integrations: Optional[str] = Query(None, description="Required integrations (comma-separated)"),
    complexity_level: Optional[str] = Query(None, description="Filter by complexity level"),
    min_rating: Optional[float] = Query(None, ge=0.0, le=5.0, description="Minimum rating"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order"),
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    community_service: CommunityService = Depends(get_community_service)
):
    """Search for workflow templates."""
    try:
        # Parse comma-separated values
        tag_list = [tag.strip() for tag in tags.split(",")] if tags else None
        integration_list = [int.strip() for int in required_integrations.split(",")] if required_integrations else None
        
        search_query = TemplateSearchQuery(
            query=query,
            category=category,
            tags=tag_list,
            required_integrations=integration_list,
            complexity_level=complexity_level,
            min_rating=min_rating,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset
        )
        
        results = await community_service.search_templates(search_query)
        return results
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/templates/popular", response_model=List[WorkflowTemplate])
async def get_popular_templates(
    limit: int = Query(10, ge=1, le=50, description="Number of templates to return"),
    community_service: CommunityService = Depends(get_community_service)
):
    """Get popular workflow templates."""
    try:
        templates = await community_service.get_popular_templates(limit)
        return templates
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get popular templates: {str(e)}")


@router.get("/templates/recent", response_model=List[WorkflowTemplate])
async def get_recent_templates(
    limit: int = Query(10, ge=1, le=50, description="Number of templates to return"),
    community_service: CommunityService = Depends(get_community_service)
):
    """Get recently published templates."""
    try:
        templates = await community_service.get_recent_templates(limit)
        return templates
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get recent templates: {str(e)}")


@router.post("/templates/{template_id}/use", response_model=TemplateAdaptationResult)
async def use_template(
    template_id: str,
    request: TemplateAdaptationRequest,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Use a template to create a new workflow."""
    try:
        result = await community_service.use_template(
            template_id=template_id,
            user_id=str(current_user.id),
            customizations=request.customizations
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to use template: {str(e)}")


@router.post("/templates/{template_id}/rate", response_model=TemplateRating)
async def rate_template(
    template_id: str,
    request: TemplateRatingRequest,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Rate a workflow template."""
    try:
        rating = await community_service.rate_template(
            template_id=template_id,
            user_id=str(current_user.id),
            rating=request.rating,
            review=request.review
        )
        
        return rating
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rate template: {str(e)}")


@router.get("/templates/{template_id}/ratings", response_model=List[TemplateRating])
async def get_template_ratings(
    template_id: str,
    limit: int = Query(20, ge=1, le=100, description="Number of ratings to return"),
    offset: int = Query(0, ge=0, description="Ratings offset"),
    community_service: CommunityService = Depends(get_community_service)
):
    """Get ratings for a template."""
    try:
        ratings = await community_service.get_template_ratings(template_id, limit, offset)
        return ratings
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ratings: {str(e)}")


@router.get("/stats", response_model=CommunityStats)
async def get_community_stats(
    community_service: CommunityService = Depends(get_community_service)
):
    """Get community statistics."""
    try:
        stats = await community_service.get_community_stats()
        return stats
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get community stats: {str(e)}")


@router.get("/categories", response_model=List[str])
async def get_template_categories():
    """Get available template categories."""
    return [category.value for category in TemplateCategory]


@router.get("/my-templates", response_model=List[WorkflowTemplate])
async def get_my_templates(
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Get templates created by the current user."""
    try:
        search_query = TemplateSearchQuery(
            created_by=str(current_user.id),
            limit=100,
            sort_by="updated_at",
            sort_order="desc"
        )
        
        results = await community_service.search_templates(search_query)
        return results.templates
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user templates: {str(e)}")


@router.post("/templates/{template_id}/publish")
async def publish_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Publish a template to the community."""
    try:
        updated_template = await community_service.update_template(
            template_id=template_id,
            updates={
                "visibility": TemplateVisibility.PUBLIC,
                "status": TemplateStatus.PUBLISHED
            },
            user_id=str(current_user.id)
        )
        
        if not updated_template:
            raise HTTPException(status_code=404, detail="Template not found or access denied")
        
        return {"message": "Template published successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish template: {str(e)}")


@router.post("/templates/{template_id}/unpublish")
async def unpublish_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    community_service: CommunityService = Depends(get_community_service)
):
    """Unpublish a template from the community."""
    try:
        updated_template = await community_service.update_template(
            template_id=template_id,
            updates={
                "visibility": TemplateVisibility.PRIVATE,
                "status": TemplateStatus.DRAFT
            },
            user_id=str(current_user.id)
        )
        
        if not updated_template:
            raise HTTPException(status_code=404, detail="Template not found or access denied")
        
        return {"message": "Template unpublished successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unpublish template: {str(e)}")