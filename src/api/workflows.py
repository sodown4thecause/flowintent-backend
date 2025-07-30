"""API endpoints for workflow management."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from ..services.temporal_service import temporal_service
from ..dependencies import get_current_user
from ..models.user import User


router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowCreateRequest(BaseModel):
    """Request model for creating a workflow."""
    workflow_type: str
    parameters: Dict[str, Any] = {}


class WorkflowResponse(BaseModel):
    """Response model for workflow operations."""
    workflow_id: str
    workflow_type: str
    status: str
    user_id: str
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowListResponse(BaseModel):
    """Response model for listing workflows."""
    workflows: List[WorkflowResponse]
    total: int


@router.post("/", response_model=WorkflowResponse)
async def create_workflow(
    request: WorkflowCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """Create and start a new workflow."""
    try:
        workflow_id = str(uuid.uuid4())
        
        # Start the workflow
        handle = await temporal_service.start_workflow(
            workflow_type=request.workflow_type,
            workflow_id=workflow_id,
            user_id=str(current_user.id),
            parameters=request.parameters
        )
        
        return WorkflowResponse(
            workflow_id=workflow_id,
            workflow_type=request.workflow_type,
            status="running",
            user_id=str(current_user.id)
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get workflow status and details."""
    try:
        status_info = await temporal_service.get_workflow_status(workflow_id)
        
        # Try to get result if completed
        result = None
        error = None
        
        if status_info["status"] == "COMPLETED":
            try:
                workflow_result = await temporal_service.get_workflow_result(workflow_id)
                if hasattr(workflow_result, 'status') and workflow_result.status == "failed":
                    error = workflow_result.error
                else:
                    result = workflow_result.result if hasattr(workflow_result, 'result') else workflow_result
            except Exception as e:
                error = str(e)
        
        return WorkflowResponse(
            workflow_id=workflow_id,
            workflow_type="unknown",  # TODO: Store workflow type in database
            status=status_info["status"].lower(),
            user_id=str(current_user.id),
            created_at=status_info["start_time"],
            completed_at=status_info["close_time"],
            result=result,
            error=error
        )
        
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {str(e)}")


@router.delete("/{workflow_id}")
async def cancel_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user)
):
    """Cancel a running workflow."""
    try:
        success = await temporal_service.cancel_workflow(workflow_id)
        
        if success:
            return {"message": f"Workflow {workflow_id} cancelled successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to cancel workflow")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling workflow: {str(e)}")


@router.get("/", response_model=WorkflowListResponse)
async def list_workflows(
    current_user: User = Depends(get_current_user),
    limit: int = 10,
    offset: int = 0
):
    """List workflows for the current user."""
    # TODO: Implement database storage for workflow metadata
    # For now, return empty list
    return WorkflowListResponse(workflows=[], total=0)


@router.post("/natural-language", response_model=WorkflowResponse)
async def create_natural_language_workflow(
    text: str,
    task_type: str = "process",
    current_user: User = Depends(get_current_user)
):
    """Create a natural language processing workflow."""
    request = WorkflowCreateRequest(
        workflow_type="natural_language",
        parameters={
            "text": text,
            "task_type": task_type,
            "model_config": {}
        }
    )
    
    return await create_workflow(request, current_user)