"""Natural language processing workflows."""

from datetime import timedelta
from typing import Any, Dict, List, Optional
from temporalio import activity, workflow
from pydantic import BaseModel

from .base import (
    BaseWorkflow, 
    WorkflowInput, 
    WorkflowResult, 
    ActivityInput, 
    ActivityResult,
    DEFAULT_RETRY_POLICY
)


class NLProcessingInput(BaseModel):
    """Input for natural language processing."""
    text: str
    task_type: str  # "summarize", "extract", "classify", etc.
    model_config: Dict[str, Any] = {}


class NLProcessingResult(BaseModel):
    """Result from natural language processing."""
    processed_text: str
    confidence: float
    metadata: Dict[str, Any] = {}


@activity.defn
async def process_natural_language(input_data: ActivityInput) -> ActivityResult:
    """Process natural language using AI models."""
    activity.logger.info(f"Processing NL for step: {input_data.step_name}")
    
    try:
        # Extract NL processing parameters
        nl_input = NLProcessingInput(**input_data.parameters)
        
        # TODO: Integrate with your AI agents/models
        # For now, return a mock result
        result = NLProcessingResult(
            processed_text=f"Processed: {nl_input.text}",
            confidence=0.95,
            metadata={
                "task_type": nl_input.task_type,
                "model_used": "mock-model",
                "processing_time": "0.5s"
            }
        )
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result=result.model_dump()
        )
        
    except Exception as e:
        activity.logger.error(f"NL processing failed: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@activity.defn
async def store_workflow_result(input_data: ActivityInput) -> ActivityResult:
    """Store workflow results in database."""
    activity.logger.info(f"Storing results for workflow: {input_data.workflow_id}")
    
    try:
        # TODO: Integrate with your database service
        # For now, return a mock result
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result={"stored": True, "record_id": f"result_{input_data.workflow_id}"}
        )
        
    except Exception as e:
        activity.logger.error(f"Failed to store results: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@workflow.defn
class NaturalLanguageWorkflow(BaseWorkflow):
    """Workflow for processing natural language tasks."""
    
    async def execute_workflow_logic(self, input_data: WorkflowInput) -> Dict[str, Any]:
        """Execute natural language processing workflow."""
        workflow.logger.info(f"Executing NL workflow: {input_data.workflow_id}")
        
        # Step 1: Process the natural language input
        nl_result = await workflow.execute_activity(
            process_natural_language,
            ActivityInput(
                workflow_id=input_data.workflow_id,
                step_name="nl_processing",
                parameters=input_data.parameters
            ),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=DEFAULT_RETRY_POLICY,
        )
        
        if nl_result.status == "failed":
            raise Exception(f"NL processing failed: {nl_result.error}")
        
        # Step 2: Store the results
        store_result = await workflow.execute_activity(
            store_workflow_result,
            ActivityInput(
                workflow_id=input_data.workflow_id,
                step_name="store_results",
                parameters={"result": nl_result.result}
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )
        
        if store_result.status == "failed":
            workflow.logger.warning(f"Failed to store results: {store_result.error}")
        
        return {
            "nl_processing": nl_result.result,
            "storage": store_result.result,
            "workflow_completed": True
        }