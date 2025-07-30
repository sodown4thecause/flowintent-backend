"""Temporal workflow for executing ExecutableWorkflow models."""

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
from ..models.workflow import ExecutableWorkflow, WorkflowStep


class ExecutableWorkflowInput(BaseModel):
    """Input for executable workflow."""
    workflow_definition: Dict[str, Any]
    execution_id: str
    context: Dict[str, Any] = {}


class StepExecutionInput(BaseModel):
    """Input for step execution activity."""
    step: Dict[str, Any]  # WorkflowStep as dict
    execution_id: str
    workflow_data: Dict[str, Any] = {}
    context: Dict[str, Any] = {}


@activity.defn
async def execute_trigger_step(input_data: ActivityInput) -> ActivityResult:
    """Execute a trigger step."""
    activity.logger.info(f"Executing trigger step: {input_data.step_name}")
    
    try:
        step_input = StepExecutionInput(**input_data.parameters)
        step = WorkflowStep(**step_input.step)
        
        # Handle different trigger types
        trigger_result = await _handle_trigger(step, step_input.context)
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result={
                "step_id": step.id,
                "step_type": "trigger",
                "trigger_data": trigger_result,
                "timestamp": activity.now().isoformat()
            }
        )
        
    except Exception as e:
        activity.logger.error(f"Trigger step failed: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@activity.defn
async def execute_action_step(input_data: ActivityInput) -> ActivityResult:
    """Execute an action step."""
    activity.logger.info(f"Executing action step: {input_data.step_name}")
    
    try:
        step_input = StepExecutionInput(**input_data.parameters)
        step = WorkflowStep(**step_input.step)
        
        # Handle different action types
        action_result = await _handle_action(step, step_input.workflow_data, step_input.context)
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result={
                "step_id": step.id,
                "step_type": "action",
                "action_result": action_result,
                "timestamp": activity.now().isoformat()
            }
        )
        
    except Exception as e:
        activity.logger.error(f"Action step failed: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@activity.defn
async def execute_condition_step(input_data: ActivityInput) -> ActivityResult:
    """Execute a condition step."""
    activity.logger.info(f"Executing condition step: {input_data.step_name}")
    
    try:
        step_input = StepExecutionInput(**input_data.parameters)
        step = WorkflowStep(**step_input.step)
        
        # Evaluate condition
        condition_result = await _handle_condition(step, step_input.workflow_data, step_input.context)
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result={
                "step_id": step.id,
                "step_type": "condition",
                "condition_met": condition_result,
                "timestamp": activity.now().isoformat()
            }
        )
        
    except Exception as e:
        activity.logger.error(f"Condition step failed: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@activity.defn
async def execute_transform_step(input_data: ActivityInput) -> ActivityResult:
    """Execute a transform step."""
    activity.logger.info(f"Executing transform step: {input_data.step_name}")
    
    try:
        step_input = StepExecutionInput(**input_data.parameters)
        step = WorkflowStep(**step_input.step)
        
        # Transform data
        transform_result = await _handle_transform(step, step_input.workflow_data, step_input.context)
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result={
                "step_id": step.id,
                "step_type": "transform",
                "transformed_data": transform_result,
                "timestamp": activity.now().isoformat()
            }
        )
        
    except Exception as e:
        activity.logger.error(f"Transform step failed: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@activity.defn
async def update_execution_progress(input_data: ActivityInput) -> ActivityResult:
    """Update workflow execution progress in database."""
    activity.logger.info(f"Updating execution progress: {input_data.workflow_id}")
    
    try:
        # TODO: Integrate with workflow service to update database
        # For now, just log the progress
        
        return ActivityResult(
            step_name=input_data.step_name,
            status="completed",
            result={"progress_updated": True}
        )
        
    except Exception as e:
        activity.logger.error(f"Failed to update progress: {str(e)}")
        return ActivityResult(
            step_name=input_data.step_name,
            status="failed",
            error=str(e)
        )


@workflow.defn
class ExecutableWorkflowRunner(BaseWorkflow):
    """Workflow for executing ExecutableWorkflow models."""
    
    async def execute_workflow_logic(self, input_data: WorkflowInput) -> Dict[str, Any]:
        """Execute the workflow steps in order."""
        workflow.logger.info(f"Executing workflow: {input_data.workflow_id}")
        
        # Parse workflow input
        exec_input = ExecutableWorkflowInput(**input_data.parameters)
        workflow_def = ExecutableWorkflow(**exec_input.workflow_definition)
        
        # Build execution order based on dependencies
        execution_order = self._build_execution_order(workflow_def.steps)
        
        workflow_data = {}
        step_results = []
        
        try:
            # Execute steps in order
            for step in execution_order:
                workflow.logger.info(f"Executing step: {step.name} ({step.type})")
                
                # Prepare step input
                step_input = StepExecutionInput(
                    step=step.dict(),
                    execution_id=exec_input.execution_id,
                    workflow_data=workflow_data,
                    context=exec_input.context
                )
                
                # Execute step based on type
                if step.type == "trigger":
                    result = await workflow.execute_activity(
                        execute_trigger_step,
                        ActivityInput(
                            workflow_id=input_data.workflow_id,
                            step_name=f"trigger_{step.id}",
                            parameters=step_input.dict()
                        ),
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                elif step.type == "action":
                    result = await workflow.execute_activity(
                        execute_action_step,
                        ActivityInput(
                            workflow_id=input_data.workflow_id,
                            step_name=f"action_{step.id}",
                            parameters=step_input.dict()
                        ),
                        start_to_close_timeout=timedelta(minutes=10),
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                elif step.type == "condition":
                    result = await workflow.execute_activity(
                        execute_condition_step,
                        ActivityInput(
                            workflow_id=input_data.workflow_id,
                            step_name=f"condition_{step.id}",
                            parameters=step_input.dict()
                        ),
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                elif step.type == "transform":
                    result = await workflow.execute_activity(
                        execute_transform_step,
                        ActivityInput(
                            workflow_id=input_data.workflow_id,
                            step_name=f"transform_{step.id}",
                            parameters=step_input.dict()
                        ),
                        start_to_close_timeout=timedelta(minutes=5),
                        retry_policy=DEFAULT_RETRY_POLICY,
                    )
                else:
                    raise ValueError(f"Unknown step type: {step.type}")
                
                if result.status == "failed":
                    # Handle step failure based on error handling configuration
                    if not self._should_continue_on_error(step, result.error):
                        raise Exception(f"Step {step.name} failed: {result.error}")
                    else:
                        workflow.logger.warning(f"Step {step.name} failed but continuing: {result.error}")
                
                # Update workflow data with step results
                if result.result:
                    workflow_data[step.id] = result.result
                    step_results.append(result.result)
                
                # Update progress in database
                await workflow.execute_activity(
                    update_execution_progress,
                    ActivityInput(
                        workflow_id=input_data.workflow_id,
                        step_name="update_progress",
                        parameters={
                            "execution_id": exec_input.execution_id,
                            "completed_steps": len(step_results),
                            "total_steps": len(workflow_def.steps),
                            "current_step": step.name
                        }
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=DEFAULT_RETRY_POLICY,
                )
            
            return {
                "execution_id": exec_input.execution_id,
                "workflow_completed": True,
                "steps_executed": len(step_results),
                "step_results": step_results,
                "final_data": workflow_data
            }
            
        except Exception as e:
            workflow.logger.error(f"Workflow execution failed: {str(e)}")
            raise
    
    def _build_execution_order(self, steps: List[WorkflowStep]) -> List[WorkflowStep]:
        """Build execution order based on step dependencies."""
        # Create a map of step ID to step
        step_map = {step.id: step for step in steps}
        
        # Topological sort to handle dependencies
        visited = set()
        temp_visited = set()
        ordered_steps = []
        
        def visit(step_id: str):
            if step_id in temp_visited:
                raise ValueError(f"Circular dependency detected involving step {step_id}")
            if step_id in visited:
                return
            
            temp_visited.add(step_id)
            step = step_map[step_id]
            
            # Visit dependencies first
            for dep_id in step.dependencies:
                if dep_id in step_map:
                    visit(dep_id)
            
            temp_visited.remove(step_id)
            visited.add(step_id)
            ordered_steps.append(step)
        
        # Visit all steps
        for step in steps:
            if step.id not in visited:
                visit(step.id)
        
        return ordered_steps
    
    def _should_continue_on_error(self, step: WorkflowStep, error: str) -> bool:
        """Determine if workflow should continue after step error."""
        error_handling = step.error_handling or {}
        return error_handling.get("continue_on_error", False)


# Helper functions for step execution
async def _handle_trigger(step: WorkflowStep, context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle trigger step execution."""
    # TODO: Implement actual trigger handling based on step configuration
    return {
        "triggered": True,
        "trigger_type": step.service or "manual",
        "trigger_data": step.configuration
    }


async def _handle_action(step: WorkflowStep, workflow_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action step execution."""
    # TODO: Implement actual action handling based on step configuration
    return {
        "action_executed": True,
        "action_type": step.service or "generic",
        "input_data": workflow_data,
        "configuration": step.configuration
    }


async def _handle_condition(step: WorkflowStep, workflow_data: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Handle condition step execution."""
    # TODO: Implement actual condition evaluation based on step configuration
    # For now, return True to continue workflow
    return True


async def _handle_transform(step: WorkflowStep, workflow_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle transform step execution."""
    # TODO: Implement actual data transformation based on step configuration
    return {
        "transformed": True,
        "original_data": workflow_data,
        "transformation": step.configuration
    }