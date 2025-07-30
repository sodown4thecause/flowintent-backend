"""Platform Agent for the Natural Language Workflow Platform.

This agent serves as the main conversational interface for the platform.
"""

from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.ag_ui import StateDeps
from ag_ui.core import EventType, StateSnapshotEvent, StateDeltaEvent, CustomEvent
from dataclasses import dataclass
import uuid
import json
from datetime import datetime

from src.models.workflow import WorkflowIntent, ExecutableWorkflow, WorkflowStep
from src.agents.orchestrator import PlatformState, handle_user_input
from src.services.vector_store import VectorStoreService
from src.services.workflow_service import WorkflowService


class PlatformResponse(BaseModel):
    """Response from the platform agent."""
    message: str = Field(description="Message to display to the user")
    workflow_id: Optional[str] = Field(None, description="ID of the created workflow")
    execution_id: Optional[str] = Field(None, description="ID of the workflow execution")
    requires_clarification: bool = Field(False, description="Whether clarification is needed")
    clarification_questions: List[str] = Field(default_factory=list, description="Questions to ask for clarification")
    next_action: str = Field("wait", description="Next action to take")


# Create the Platform Agent
platform_agent = Agent[StateDeps[PlatformState], PlatformResponse](
    model='openai:gpt-4o',
    deps_type=StateDeps[PlatformState],
    output_type=PlatformResponse,
    system_prompt="""
    You are the Platform Agent for a Natural Language Workflow Platform.
    
    Your job is to help users create, manage, and execute workflows using natural language.
    You should guide users through the workflow creation process, asking for clarification
    when needed and providing helpful feedback.
    
    The platform allows users to:
    1. Create workflows by describing what they want to accomplish
    2. Execute workflows and monitor their progress
    3. Manage existing workflows and view their results
    4. Connect to external services like Google Drive, Slack, etc.
    
    You should be helpful, informative, and guide the user through the process.
    """
)


@platform_agent.tool
async def update_state(
    ctx: RunContext[StateDeps[PlatformState]], 
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


@platform_agent.tool
async def send_progress_update(
    ctx: RunContext[StateDeps[PlatformState]],
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


@platform_agent.tool
async def process_user_request(
    ctx: RunContext[StateDeps[PlatformState]],
    user_input: str,
    vector_store: VectorStoreService,
    workflow_service: WorkflowService
) -> Dict[str, Any]:
    """Process the user's request using the orchestrator."""
    result = await handle_user_input(
        user_input=user_input,
        state=ctx.deps.state,
        vector_store=vector_store,
        workflow_service=workflow_service
    )
    
    # Update state with orchestrator result
    if result.get("state"):
        await update_state(ctx, result["state"])
    
    return result


@platform_agent.tool
async def show_workflow_details(
    ctx: RunContext[StateDeps[PlatformState]],
    workflow: Dict[str, Any]
) -> CustomEvent:
    """Show workflow details in the UI."""
    return CustomEvent(
        type=EventType.CUSTOM,
        name="workflow_details",
        value=workflow
    )


@platform_agent.tool
async def request_confirmation(
    ctx: RunContext[StateDeps[PlatformState]],
    message: str,
    action: str
) -> CustomEvent:
    """Request confirmation from the user."""
    return CustomEvent(
        type=EventType.CUSTOM,
        name="confirmation_request",
        value={
            "message": message,
            "action": action
        }
    )


def create_platform_agent_app():
    """Create an AG-UI app from the platform agent."""
    from pydantic_ai.ag_ui import mount_ag_ui
    from fastapi import FastAPI
    
    # Create initial state
    initial_state = PlatformState(
        user_id="",
        conversation_id=str(uuid.uuid4()),
        workflow_status="idle"
    )
    
    # Create AG-UI app
    app = platform_agent.to_ag_ui(
        deps=StateDeps(initial_state)
    )
    
    return app