"""Workflow Builder Agent for the Natural Language Workflow Platform.

This agent is responsible for converting workflow intents into executable workflows.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, ModelRetry
from dataclasses import dataclass

from src.models.workflow import WorkflowIntent, ExecutableWorkflow, WorkflowStep
from src.services.vector_store import VectorStoreService


@dataclass
class WorkflowBuilderDeps:
    """Dependencies for the Workflow Builder Agent."""
    vector_store: VectorStoreService
    user_id: str
    available_integrations: List[Dict[str, Any]] = None


class WorkflowBuildResult(BaseModel):
    """Result of workflow building."""
    workflow: ExecutableWorkflow = Field(description="Built executable workflow")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for the built workflow")
    estimated_runtime: int = Field(description="Estimated runtime in seconds")
    required_integrations: List[str] = Field(description="Required integrations for this workflow")
    warnings: List[str] = Field(default_factory=list, description="Warnings about potential issues")


# Create the Workflow Builder Agent
workflow_builder = Agent[WorkflowBuilderDeps, WorkflowBuildResult](
    model='openai:gpt-4o',
    deps_type=WorkflowBuilderDeps,
    output_type=WorkflowBuildResult,
    system_prompt="""
    You are a Workflow Builder Agent for a Natural Language Workflow Platform.
    Your job is to convert workflow intents into executable workflows with well-defined steps.
    
    An executable workflow consists of:
    1. A series of ordered steps with clear inputs and outputs
    2. Proper dependency management between steps
    3. Error handling and recovery strategies
    4. Required integrations and permissions
    
    You should create workflows that are efficient, reliable, and accomplish the user's intent.
    Validate that all dependencies between steps are properly defined and there are no circular dependencies.
    """
)


@workflow_builder.tool
async def search_workflow_steps(ctx: RunContext[WorkflowBuilderDeps], query: str) -> List[Dict[str, Any]]:
    """Search for reusable workflow steps in the vector database."""
    if not ctx.deps.vector_store:
        return []
    
    results = await ctx.deps.vector_store.search(
        query=query,
        collection_type="steps",
        limit=5,
        threshold=0.7
    )
    
    return [
        {
            "id": result.content.get("id", "unknown"),
            "name": result.content.get("name", "Unnamed step"),
            "description": result.content.get("description", ""),
            "inputs": result.content.get("inputs", {}),
            "outputs": result.content.get("outputs", {}),
            "similarity_score": result.score
        }
        for result in results
    ]


@workflow_builder.tool
async def get_available_integrations(ctx: RunContext[WorkflowBuilderDeps]) -> List[Dict[str, Any]]:
    """Get the list of available integrations for the user."""
    if ctx.deps.available_integrations:
        return ctx.deps.available_integrations
    
    # Default integrations if none provided
    return [
        {"name": "google_drive", "status": "available", "capabilities": ["read", "write", "list"]},
        {"name": "google_sheets", "status": "available", "capabilities": ["read", "write", "append"]},
        {"name": "slack", "status": "available", "capabilities": ["send_message", "read_channel"]},
        {"name": "openai", "status": "available", "capabilities": ["generate_text", "generate_image"]}
    ]


@workflow_builder.output_validator
async def validate_workflow(ctx: RunContext[WorkflowBuilderDeps], result: WorkflowBuildResult) -> WorkflowBuildResult:
    """Validate the built workflow for correctness."""
    workflow = result.workflow
    
    # Check for circular dependencies
    step_ids = {step.id for step in workflow.steps}
    for step in workflow.steps:
        for dep in step.depends_on:
            if dep not in step_ids:
                raise ModelRetry(f"Step {step.id} depends on non-existent step {dep}")
    
    # Check that all required integrations are available
    available_integrations = {
        integration["name"] for integration in await get_available_integrations(ctx)
    }
    
    missing_integrations = []
    for integration in result.required_integrations:
        if integration not in available_integrations:
            missing_integrations.append(integration)
    
    if missing_integrations:
        result.warnings.append(f"Missing integrations: {', '.join(missing_integrations)}")
    
    return result


async def build_workflow(
    intent: WorkflowIntent,
    vector_store: VectorStoreService,
    user_id: str,
    available_integrations: List[Dict[str, Any]] = None
) -> WorkflowBuildResult:
    """Build an executable workflow from a workflow intent."""
    deps = WorkflowBuilderDeps(
        vector_store=vector_store,
        user_id=user_id,
        available_integrations=available_integrations
    )
    
    # Convert intent to a prompt for the workflow builder
    prompt = f"""
    Build a workflow for the following intent:
    
    Goal: {intent.goal}
    Input Data: {intent.input_data}
    Expected Output: {intent.expected_output}
    Constraints: {intent.constraints}
    
    Create a detailed executable workflow with clear steps, dependencies, and error handling.
    """
    
    result = await workflow_builder.run(prompt, deps=deps)
    return result.output