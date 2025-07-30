"""Enhanced API endpoints for workflow management with ExecutableWorkflow support."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel

from ..models.workflow import (
    ExecutableWorkflow, 
    WorkflowExecution, 
    WorkflowContext,
    WorkflowStep,
    WorkflowIntent
)
from ..services.workflow_service import WorkflowService, get_workflow_service
from ..dependencies import get_current_user
from ..models.user import User


router = APIRouter(prefix="/workflow-management", tags=["workflow-management"])


class CreateWorkflowRequest(BaseModel):
    """Request model for creating a workflow."""
    name: str
    description: str
    steps: List[WorkflowStep]
    schedule: Optional[str] = None
    enabled: bool = True
    estimated_runtime: int = 60  # seconds


class ExecuteWorkflowRequest(BaseModel):
    """Request model for executing a workflow."""
    context: Optional[WorkflowContext] = None


class WorkflowIntentRequest(BaseModel):
    """Request model for creating workflow from natural language intent."""
    description: str
    requirements: Optional[str] = None
    expected_output: Optional[str] = None


@router.post("/", response_model=ExecutableWorkflow)
async def create_workflow(
    request: CreateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Create a new executable workflow."""
    try:
        workflow = ExecutableWorkflow(
            name=request.name,
            description=request.description,
            steps=request.steps,
            schedule=request.schedule,
            enabled=request.enabled,
            estimated_runtime=request.estimated_runtime
        )
        
        created_workflow = await workflow_service.create_workflow(
            workflow=workflow,
            user_id=str(current_user.id)
        )
        
        return created_workflow
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.get("/", response_model=List[ExecutableWorkflow])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
    limit: int = 10,
    offset: int = 0
):
    """List workflows for the current user."""
    try:
        workflows = await workflow_service.list_workflows(
            user_id=str(current_user.id),
            limit=limit,
            offset=offset
        )
        return workflows
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list workflows: {str(e)}")


@router.get("/{workflow_id}", response_model=ExecutableWorkflow)
async def get_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Get a specific workflow."""
    try:
        workflow = await workflow_service.get_workflow(
            workflow_id=workflow_id,
            user_id=str(current_user.id)
        )
        
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        return workflow
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get workflow: {str(e)}")


@router.post("/{workflow_id}/execute", response_model=WorkflowExecution)
async def execute_workflow(
    workflow_id: str,
    request: ExecuteWorkflowRequest,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Execute a workflow."""
    try:
        execution = await workflow_service.execute_workflow(
            workflow_id=workflow_id,
            user_id=str(current_user.id),
            context=request.context
        )
        
        return execution
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute workflow: {str(e)}")


@router.get("/{workflow_id}/executions", response_model=List[WorkflowExecution])
async def list_workflow_executions(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service),
    limit: int = 10,
    offset: int = 0
):
    """List executions for a specific workflow."""
    try:
        executions = await workflow_service.list_executions(
            user_id=str(current_user.id),
            workflow_id=workflow_id,
            limit=limit,
            offset=offset
        )
        
        return executions
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list executions: {str(e)}")


@router.get("/executions/{execution_id}", response_model=WorkflowExecution)
async def get_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Get details of a specific workflow execution."""
    try:
        execution = await workflow_service.get_execution(
            execution_id=execution_id,
            user_id=str(current_user.id)
        )
        
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        return execution
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get execution: {str(e)}")


@router.delete("/executions/{execution_id}")
async def cancel_execution(
    execution_id: str,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Cancel a running workflow execution."""
    try:
        success = await workflow_service.cancel_execution(
            execution_id=execution_id,
            user_id=str(current_user.id)
        )
        
        if success:
            return {"message": f"Execution {execution_id} cancelled successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to cancel execution")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cancelling execution: {str(e)}")


@router.post("/from-intent", response_model=ExecutableWorkflow)
async def create_workflow_from_intent(
    request: WorkflowIntentRequest,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Create a workflow from natural language intent (AI-powered)."""
    try:
        # TODO: Integrate with AI agents to parse intent and generate workflow
        # For now, create a simple example workflow
        
        steps = [
            WorkflowStep(
                name="Start",
                type="trigger",
                service="manual",
                configuration={"description": request.description}
            ),
            WorkflowStep(
                name="Process",
                type="action",
                service="ai_processing",
                configuration={
                    "task": "process_intent",
                    "input": request.description,
                    "requirements": request.requirements or ""
                },
                dependencies=[]
            ),
            WorkflowStep(
                name="Output",
                type="transform",
                service="formatter",
                configuration={
                    "format": request.expected_output or "json",
                    "template": "default"
                },
                dependencies=[]
            )
        ]
        
        workflow = ExecutableWorkflow(
            name=f"AI Generated: {request.description[:50]}...",
            description=f"Workflow generated from: {request.description}",
            steps=steps,
            estimated_runtime=120
        )
        
        created_workflow = await workflow_service.create_workflow(
            workflow=workflow,
            user_id=str(current_user.id)
        )
        
        return created_workflow
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow from intent: {str(e)}")


@router.get("/templates/", response_model=List[ExecutableWorkflow])
async def get_workflow_templates():
    """Get predefined workflow templates."""
    templates = [
        ExecutableWorkflow(
            id="template_data_processing",
            name="Data Processing Pipeline",
            description="Process and transform data from various sources",
            steps=[
                WorkflowStep(
                    name="Data Ingestion",
                    type="trigger",
                    service="data_source",
                    configuration={"source_type": "api", "endpoint": ""}
                ),
                WorkflowStep(
                    name="Data Validation",
                    type="condition",
                    service="validator",
                    configuration={"rules": []},
                    dependencies=[]
                ),
                WorkflowStep(
                    name="Data Transformation",
                    type="transform",
                    service="transformer",
                    configuration={"operations": []},
                    dependencies=[]
                ),
                WorkflowStep(
                    name="Data Output",
                    type="action",
                    service="data_sink",
                    configuration={"destination": "database"},
                    dependencies=[]
                )
            ],
            estimated_runtime=300
        ),
        ExecutableWorkflow(
            id="template_notification",
            name="Smart Notification System",
            description="Send intelligent notifications based on conditions",
            steps=[
                WorkflowStep(
                    name="Monitor Trigger",
                    type="trigger",
                    service="monitor",
                    configuration={"check_interval": 300}
                ),
                WorkflowStep(
                    name="Evaluate Conditions",
                    type="condition",
                    service="evaluator",
                    configuration={"conditions": []},
                    dependencies=[]
                ),
                WorkflowStep(
                    name="Generate Message",
                    type="transform",
                    service="ai_writer",
                    configuration={"template": "notification"},
                    dependencies=[]
                ),
                WorkflowStep(
                    name="Send Notification",
                    type="action",
                    service="notifier",
                    configuration={"channels": ["email", "slack"]},
                    dependencies=[]
                )
            ],
            estimated_runtime=60
        )
    ]
    
    return templates