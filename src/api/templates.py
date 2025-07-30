"""
API endpoints for workflow templates.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel

from src.dependencies import get_db_pool, get_vector_store_service
from src.models.template import (
    WorkflowTemplate, 
    WorkflowTemplateSearchResult,
    WorkflowTemplateImport,
    WorkflowTemplateExport
)
from src.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])

async def get_template_service(
    db_pool=Depends(get_db_pool),
    vector_store_service=Depends(get_vector_store_service)
):
    """Get template service dependency."""
    return TemplateService(db_pool, vector_store_service)

class TemplateSearchRequest(BaseModel):
    """Request model for template search."""
    query: str
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    limit: int = 10

class TemplateResponse(BaseModel):
    """Response model for template operations."""
    message: str
    template_id: Optional[str] = None
    workflow_id: Optional[str] = None

@router.post("/search", response_model=List[WorkflowTemplateSearchResult])
async def search_templates(
    search_request: TemplateSearchRequest,
    template_service: TemplateService = Depends(get_template_service)
):
    """Search for workflow templates."""
    results = await template_service.search_templates(
        query=search_request.query,
        category=search_request.category,
        tags=search_request.tags,
        limit=search_request.limit
    )
    return results

@router.get("/featured", response_model=List[WorkflowTemplateSearchResult])
async def get_featured_templates(
    limit: int = Query(10, ge=1, le=50),
    template_service: TemplateService = Depends(get_template_service)
):
    """Get featured workflow templates."""
    results = await template_service.get_featured_templates(limit=limit)
    return results

@router.get("/category/{category}", response_model=List[WorkflowTemplateSearchResult])
async def get_templates_by_category(
    category: str,
    limit: int = Query(10, ge=1, le=50),
    template_service: TemplateService = Depends(get_template_service)
):
    """Get workflow templates by category."""
    results = await template_service.get_templates_by_category(
        category=category,
        limit=limit
    )
    return results

@router.get("/{template_id}", response_model=WorkflowTemplate)
async def get_template(
    template_id: str,
    template_service: TemplateService = Depends(get_template_service)
):
    """Get a workflow template by ID."""
    try:
        template = await template_service.get_template(template_id)
        return template
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get template: {str(e)}")

@router.post("/import", response_model=dict)
async def import_template(
    import_request: WorkflowTemplateImport,
    template_service: TemplateService = Depends(get_template_service)
):
    """Import a workflow template."""
    try:
        result = await template_service.import_template(import_request)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import template: {str(e)}")

@router.post("/export", response_model=TemplateResponse)
async def export_as_template(
    export_request: WorkflowTemplateExport,
    template_service: TemplateService = Depends(get_template_service)
):
    """Export a workflow as a template."""
    try:
        template_id = await template_service.export_as_template(export_request)
        return TemplateResponse(
            message=f"Successfully exported workflow as template",
            template_id=template_id
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export template: {str(e)}")

@router.post("/seed", response_model=TemplateResponse)
async def seed_templates(
    directory_path: str = Body(..., embed=True),
    template_service: TemplateService = Depends(get_template_service)
):
    """Seed templates from a directory."""
    try:
        count = await template_service.seed_templates_from_directory(directory_path)
        return TemplateResponse(
            message=f"Successfully seeded {count} templates"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to seed templates: {str(e)}")