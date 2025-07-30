"""Intent Parser Agent for the Natural Language Workflow Platform.

This agent is responsible for parsing natural language input into structured workflow intents.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

from src.services.vector_store import VectorStoreService
from src.models.workflow import WorkflowIntent, WorkflowStep


@dataclass
class IntentParserDeps:
    """Dependencies for the Intent Parser Agent."""
    vector_store: VectorStoreService
    user_id: str
    user_preferences: Dict[str, Any] = None


class IntentParsingResult(BaseModel):
    """Result of intent parsing."""
    intent: WorkflowIntent = Field(description="Parsed workflow intent")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for the parsed intent")
    requires_clarification: bool = Field(description="Whether clarification is needed from the user")
    clarification_questions: List[str] = Field(default_factory=list, description="Questions to ask the user for clarification")
    similar_workflows: List[Dict[str, Any]] = Field(default_factory=list, description="Similar workflows found in the database")


# Create the Intent Parser Agent
intent_parser = Agent[IntentParserDeps, IntentParsingResult](
    model='openai:gpt-4o',
    deps_type=IntentParserDeps,
    output_type=IntentParsingResult,
    system_prompt="""
    You are an Intent Parser Agent for a Natural Language Workflow Platform.
    Your job is to analyze user requests and convert them into structured workflow intents.
    
    A workflow intent consists of:
    1. A clear goal or objective
    2. Input data requirements
    3. Expected output format
    4. Any constraints or preferences
    
    You should identify the user's intent with high precision and structure it properly.
    If the request is ambiguous, identify what clarification is needed.
    """
)


@intent_parser.tool
async def search_similar_workflows(ctx: RunContext[IntentParserDeps], query: str) -> List[Dict[str, Any]]:
    """Search for similar workflows in the vector database."""
    if not ctx.deps.vector_store:
        return []
    
    results = await ctx.deps.vector_store.search(
        query=query,
        collection_type="workflows",
        limit=3,
        threshold=0.7
    )
    
    return [
        {
            "id": result.content.get("id", "unknown"),
            "name": result.content.get("name", "Unnamed workflow"),
            "description": result.content.get("description", ""),
            "similarity_score": result.score
        }
        for result in results
    ]


@intent_parser.tool
async def get_user_preferences(ctx: RunContext[IntentParserDeps]) -> Dict[str, Any]:
    """Get the user's preferences to inform intent parsing."""
    if ctx.deps.user_preferences:
        return ctx.deps.user_preferences
    return {"default_preferences": True}


async def parse_intent(
    user_input: str,
    vector_store: VectorStoreService,
    user_id: str,
    user_preferences: Dict[str, Any] = None
) -> IntentParsingResult:
    """Parse user input into a structured workflow intent."""
    deps = IntentParserDeps(
        vector_store=vector_store,
        user_id=user_id,
        user_preferences=user_preferences
    )
    
    result = await intent_parser.run(user_input, deps=deps)
    return result.output