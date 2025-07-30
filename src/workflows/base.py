"""Base workflow definitions and activities for Temporal."""

from datetime import timedelta
from typing import Any, Dict, List, Optional
from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from pydantic import BaseModel


class WorkflowInput(BaseModel):
    """Base input model for workflows."""
    workflow_id: str
    user_id: str
    parameters: Dict[str, Any] = {}


class WorkflowResult(BaseModel):
    """Base result model for workflows."""
    workflow_id: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ActivityInput(BaseModel):
    """Base input model for activities."""
    workflow_id: str
    step_name: str
    parameters: Dict[str, Any] = {}


class ActivityResult(BaseModel):
    """Base result model for activities."""
    step_name: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# Default retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
    backoff_coefficient=2.0,
)


@activity.defn
async def log_activity(input_data: ActivityInput) -> ActivityResult:
    """Basic logging activity for workflow steps."""
    activity.logger.info(
        f"Executing step: {input_data.step_name} for workflow: {input_data.workflow_id}"
    )
    
    return ActivityResult(
        step_name=input_data.step_name,
        status="completed",
        result={"logged": True, "timestamp": activity.now().isoformat()}
    )


@workflow.defn
class BaseWorkflow:
    """Base workflow class with common functionality."""
    
    @workflow.run
    async def run(self, input_data: WorkflowInput) -> WorkflowResult:
        """Base workflow execution."""
        workflow.logger.info(f"Starting workflow: {input_data.workflow_id}")
        
        try:
            # Log the workflow start
            log_result = await workflow.execute_activity(
                log_activity,
                ActivityInput(
                    workflow_id=input_data.workflow_id,
                    step_name="workflow_start",
                    parameters=input_data.parameters
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            
            # Override this method in subclasses
            result = await self.execute_workflow_logic(input_data)
            
            return WorkflowResult(
                workflow_id=input_data.workflow_id,
                status="completed",
                result=result
            )
            
        except Exception as e:
            workflow.logger.error(f"Workflow {input_data.workflow_id} failed: {str(e)}")
            return WorkflowResult(
                workflow_id=input_data.workflow_id,
                status="failed",
                error=str(e)
            )
    
    async def execute_workflow_logic(self, input_data: WorkflowInput) -> Dict[str, Any]:
        """Override this method in subclasses to implement workflow logic."""
        return {"message": "Base workflow completed"}