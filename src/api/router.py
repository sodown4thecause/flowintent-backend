"""Main API router for the Natural Language Workflow Platform."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Any, List

from src.services.database import DatabaseService, get_db
from src.dependencies import WorkflowDependencies, get_dependencies
from .workflows import router as workflows_router
from .workflow_management import router as workflow_management_router
from .workflow_recommendations import router as workflow_recommendations_router
from .dashboard import router as dashboard_router
from .integrations import router as integrations_router
from .natural_language_workflows import router as nl_workflows_router
from .community import router as community_router
from .research import router as research_router
from .auth import router as auth_router
from .templates import router as templates_router
from .optimization import router as optimization_router

# Create main API router
api_router = APIRouter(prefix="/api/v1")

# Include authentication router
api_router.include_router(auth_router)

# Include workflow routers
api_router.include_router(workflows_router)
api_router.include_router(workflow_management_router)
api_router.include_router(workflow_recommendations_router)
api_router.include_router(dashboard_router)
api_router.include_router(integrations_router)
api_router.include_router(nl_workflows_router)
api_router.include_router(community_router)
api_router.include_router(research_router)
api_router.include_router(templates_router)
api_router.include_router(optimization_router)

# Health check endpoint
@api_router.get("/health")
async def api_health_check(db: DatabaseService = Depends(get_db)):
    """API health check endpoint."""
    try:
        await db.fetchval("SELECT 1")
        return {"status": "healthy", "message": "API is operational"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "message": str(e)}
        )

# API version info endpoint
@api_router.get("/info")
async def api_info():
    """Get API version and information."""
    return {
        "name": "Natural Language Workflow Platform API",
        "version": "0.1.0",
        "features": [
            "Workflow Management",
            "Natural Language Processing",
            "Service Integrations",
            "Temporal Workflows",
            "Vector Search"
        ]
    }