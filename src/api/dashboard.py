"""Dashboard routes for the Natural Language Workflow Platform."""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Dict, Any, List
import random
from datetime import datetime, timedelta

from ..dependencies import get_current_user
from ..models.user import User
from ..services.workflow_service import WorkflowService, get_workflow_service
from ..services.vector_store import VectorStoreService, get_vector_store


# Set up templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Render the dashboard page."""
    try:
        # Get user's workflows
        user_workflows = await workflow_service.list_workflows(
            user_id=str(current_user.id),
            limit=10
        )
        
        # Get user's workflow executions
        executions = await workflow_service.list_executions(
            user_id=str(current_user.id),
            limit=10
        )
        
        # Get recommended templates from vector store
        templates_items = await vector_store.list_items(
            collection_type="workflows",
            limit=6
        )
        
        # Format data for the template
        recent_workflows = []
        for workflow in user_workflows:
            status_map = {
                True: "active",
                False: "inactive"
            }
            status_color_map = {
                True: "success",
                False: "secondary"
            }
            
            recent_workflows.append({
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "status": status_map.get(workflow.enabled, "unknown"),
                "status_color": status_color_map.get(workflow.enabled, "secondary"),
                "steps": [step.name for step in workflow.steps[:3]],
                "created_at": workflow.created_at
            })
        
        # Format executions
        recent_executions = []
        for execution in executions:
            # Calculate duration
            duration = "N/A"
            if execution.completed_at and execution.started_at:
                duration_seconds = execution.execution_time or 0
                if duration_seconds < 60:
                    duration = f"{duration_seconds}s"
                else:
                    duration = f"{duration_seconds // 60}m {duration_seconds % 60}s"
            
            recent_executions.append({
                "id": execution.id[:8],
                "workflow_name": execution.workflow_id,  # Ideally, get the actual name
                "started_at": execution.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                "duration": duration,
                "status": execution.status.capitalize()
            })
        
        # Format recommended templates
        recommended_templates = []
        for item in templates_items:
            content = item["content"]
            recommended_templates.append({
                "id": item["id"],
                "name": content.get("name", "Unnamed Template"),
                "description": content.get("description", ""),
                "category": content.get("category", "general"),
                "tags": content.get("tags", [])[:3]
            })
        
        # Dashboard statistics
        total_workflows = len(user_workflows)
        active_workflows = sum(1 for w in user_workflows if w.enabled)
        
        # For demo purposes, generate some random stats
        executions_today = random.randint(5, 20)
        success_rate = random.randint(80, 100)
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "total_workflows": total_workflows,
                "active_workflows": active_workflows,
                "executions_today": executions_today,
                "success_rate": success_rate,
                "recent_workflows": recent_workflows,
                "recent_executions": recent_executions,
                "recommended_templates": recommended_templates
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {str(e)}")