"""Orchestrator Agent for the Natural Language Workflow Platform.

This agent coordinates the multi-agent system and manages conversation flow.
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.ag_ui import StateDeps
from ag_ui.core import EventType, StateSnapshotEvent, StateDeltaEvent, CustomEvent
from dataclasses import dataclass
import uuid
import json
from datetime import datetime

from src.agents.intent_parser import parse_intent, IntentParsingResult
from src.agents.workflow_builder import build_workflow, WorkflowBuildResult
from src.models.workflow import WorkflowIntent, ExecutableWorkflow, WorkflowStep
from src.services.vector_store import VectorStoreService
from src.services.workflow_service import WorkflowService


class PlatformState(BaseModel):
    """State for the platform agent."""
    user_id: str = Field(default="")
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_intent: Optional[WorkflowIntent] = None
    current_workflow: Optional[ExecutableWorkflow] = None
    workflow_status: str = Field(default="idle")
    available_integrations: List[Dict[str, Any]] = Field(default_factory=list)
    execution_progress: Dict[str, Any] = Field(default_factory=dict)
    needs_clarification: bool = Field(default=False)
    clarification_questions: List[str] = Field(default_factory=list)


@dataclass
class OrchestratorDeps:
    """Dependencies for the Orchestrator Agent."""
    state: PlatformState
    vector_store: VectorStoreService
    workflow_service: WorkflowService


class OrchestratorAction(BaseModel):
    """Action to be taken by the orchestrator."""
    action_type: str = Field(description="Type of action to take")
    message: str = Field(description="Message to display to the user")
    state_updates: Dict[str, Any] = Field(default_factory=dict, description="Updates to make to the platform state")
    next_step: str = Field(description="Next step in the conversation flow")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Events to send to the frontend")


# Create the Orchestrator Agent
orchestrator_agent = Agent[OrchestratorDeps, OrchestratorAction](
    model='openai:gpt-4o',
    deps_type=OrchestratorDeps,
    output_type=OrchestratorAction,
    system_prompt="""
    You are an Orchestrator Agent for a Natural Language Workflow Platform.
    Your job is to coordinate the conversation flow and delegate tasks to specialized agents.
    
    You manage the overall user experience and ensure the user's intent is properly understood
    and executed. You should guide the user through the workflow creation and execution process,
    asking for clarification when needed and providing helpful feedback.
    
    The platform follows these main steps:
    1. Parse the user's intent using the Intent Parser Agent
    2. Build an executable workflow using the Workflow Builder Agent
    3. Execute the workflow using the Workflow Execution Service
    4. Report results back to the user
    
    You should maintain a coherent conversation flow and provide clear, helpful responses.
    """
)


@orchestrator_agent.tool
async def update_platform_state(
    ctx: RunContext[OrchestratorDeps], 
    updates: Dict[str, Any]
) -> StateSnapshotEvent:
    """Update the platform state."""
    # Create a copy of the current state
    current_state = ctx.deps.state.model_dump()
    
    # Apply updates
    for key, value in updates.items():
        if key in current_state:
            current_state[key] = value
    
    # Create new state
    new_state = PlatformState(**current_state)
    
    # Return state snapshot event
    return StateSnapshotEvent(
        type=EventType.STATE_SNAPSHOT,
        snapshot=new_state.model_dump()
    )


@orchestrator_agent.tool
async def process_user_intent(
    ctx: RunContext[OrchestratorDeps], 
    user_input: str
) -> IntentParsingResult:
    """Process the user's input to extract their intent."""
    result = await parse_intent(
        user_input=user_input,
        vector_store=ctx.deps.vector_store,
        user_id=ctx.deps.state.user_id,
        user_preferences={}  # Add user preferences here
    )
    
    # Update state with the parsed intent
    await update_platform_state(ctx, {
        "current_intent": result.intent.model_dump(),
        "needs_clarification": result.requires_clarification,
        "clarification_questions": result.clarification_questions
    })
    
    return result


@orchestrator_agent.tool
async def build_executable_workflow(
    ctx: RunContext[OrchestratorDeps]
) -> WorkflowBuildResult:
    """Build an executable workflow from the current intent."""
    if not ctx.deps.state.current_intent:
        raise ValueError("No current intent available")
    
    intent = WorkflowIntent(**ctx.deps.state.current_intent)
    
    result = await build_workflow(
        intent=intent,
        vector_store=ctx.deps.vector_store,
        user_id=ctx.deps.state.user_id,
        available_integrations=ctx.deps.state.available_integrations
    )
    
    # Update state with the built workflow
    await update_platform_state(ctx, {
        "current_workflow": result.workflow.model_dump(),
        "workflow_status": "built"
    })
    
    return result


@orchestrator_agent.tool
async def execute_workflow(
    ctx: RunContext[OrchestratorDeps]
) -> Dict[str, Any]:
    """Execute the current workflow."""
    if not ctx.deps.state.current_workflow:
        raise ValueError("No current workflow available")
    
    workflow = ExecutableWorkflow(**ctx.deps.state.current_workflow)
    
    # Update state to indicate workflow is running
    await update_platform_state(ctx, {
        "workflow_status": "running",
        "execution_progress": {
            "status": "started",
            "start_time": datetime.now().isoformat(),
            "completed_steps": 0,
            "total_steps": len(workflow.steps)
        }
    })
    
    # Execute the workflow
    execution_id = await ctx.deps.workflow_service.execute_workflow(
        workflow=workflow,
        user_id=ctx.deps.state.user_id
    )
    
    # In a real implementation, we would monitor the workflow execution
    # and update the state as steps complete. For now, we'll simulate completion.
    
    # Update state to indicate workflow is complete
    await update_platform_state(ctx, {
        "workflow_status": "completed",
        "execution_progress": {
            "status": "completed",
            "end_time": datetime.now().isoformat(),
            "completed_steps": len(workflow.steps),
            "total_steps": len(workflow.steps),
            "execution_id": execution_id
        }
    })
    
    return {
        "execution_id": execution_id,
        "status": "completed",
        "message": "Workflow executed successfully"
    }


@orchestrator_agent.tool
async def send_progress_update(
    ctx: RunContext[OrchestratorDeps],
    step: int,
    total: int,
    message: str
) -> CustomEvent:
    """Send a progress update to the frontend."""
    return CustomEvent(
        type=EventType.CUSTOM,
        name="progress_update",
        value={
            "step": step,
            "total": total,
            "percentage": (step / total) * 100,
            "message": message
        }
    )


async def handle_user_input(
    user_input: str,
    state: PlatformState,
    vector_store: VectorStoreService,
    workflow_service: WorkflowService
) -> Dict[str, Any]:
    """Handle user input and coordinate the multi-agent workflow."""
    deps = OrchestratorDeps(
        state=state,
        vector_store=vector_store,
        workflow_service=workflow_service
    )
    
    # Process the user input
    result = await orchestrator_agent.run(user_input, deps=deps)
    
    # Return the result
    return {
        "action": result.output.action_type,
        "message": result.output.message,
        "next_step": result.output.next_step,
        "state": state.model_dump()
    }