"""
Agent for understanding and generating workflow templates from natural language.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.models.template import WorkflowTemplate, WorkflowNode, WorkflowNodeConnection

class TemplateIntent(BaseModel):
    """Intent for creating a workflow template."""
    name: str = Field(description="Name of the workflow")
    description: str = Field(description="Description of what the workflow does")
    category: str = Field(description="Category of the workflow (e.g., 'Social Media', 'Research', 'Data Processing')")
    required_integrations: List[str] = Field(description="List of required integrations (e.g., 'Telegram', 'OpenAI', 'Google Sheets')")
    workflow_steps: List[str] = Field(description="List of steps in the workflow")
    input_trigger: str = Field(description="What triggers the workflow (e.g., 'message received', 'scheduled', 'webhook')")
    output_action: str = Field(description="Final action of the workflow (e.g., 'send message', 'update database')")
    complexity: float = Field(ge=0.0, le=1.0, description="Estimated complexity of the workflow")

class WorkflowDependencies:
    """Dependencies for workflow template agent."""
    def __init__(self, db_conn, vector_store, template_service):
        self.db_conn = db_conn
        self.vector_store = vector_store
        self.template_service = template_service

template_intent_agent = Agent[WorkflowDependencies, TemplateIntent](
    model='openai:gpt-4o',
    deps_type=WorkflowDependencies,
    output_type=TemplateIntent,
    system_prompt="""
    You are a workflow template expert. Your job is to analyze natural language descriptions
    of workflows and extract structured information about what the user wants to build.
    
    Focus on understanding:
    1. The overall purpose of the workflow
    2. Required integrations and services
    3. The trigger that starts the workflow
    4. The sequence of steps in the workflow
    5. The final output or action
    
    Be thorough in identifying all components while maintaining high confidence.
    """
)

@template_intent_agent.tool
async def search_similar_templates(ctx: RunContext[WorkflowDependencies], description: str) -> List[Dict]:
    """Search for similar workflow templates."""
    results = await ctx.deps.vector_store.search_templates(
        query_text=description,
        limit=5
    )
    return [{"template": r.content, "similarity": r.score} for r in results]

@template_intent_agent.tool
async def get_available_integrations(ctx: RunContext[WorkflowDependencies]) -> List[str]:
    """Get list of available integrations."""
    rows = await ctx.deps.db_conn.fetch(
        """
        SELECT DISTINCT name FROM integrations
        """
    )
    return [row["name"] for row in rows]

template_generator_agent = Agent[WorkflowDependencies, WorkflowTemplate](
    model='openai:gpt-4o',
    deps_type=WorkflowDependencies,
    output_type=WorkflowTemplate,
    system_prompt="""
    You are a workflow template generator. Your job is to create detailed workflow templates
    based on user requirements and intent analysis.
    
    For each template, you need to:
    1. Define the nodes (components) needed in the workflow
    2. Configure each node with appropriate parameters
    3. Define connections between nodes
    4. Provide natural language descriptions of the workflow
    
    Create robust workflows that handle edge cases and follow best practices.
    """
)

@template_generator_agent.tool
async def get_integration_details(ctx: RunContext[WorkflowDependencies], integration_name: str) -> Dict:
    """Get details about an integration."""
    row = await ctx.deps.db_conn.fetchrow(
        """
        SELECT * FROM integrations WHERE name = $1
        """,
        integration_name
    )
    
    if not row:
        return {"error": f"Integration {integration_name} not found"}
        
    return {
        "name": row["name"],
        "description": row["description"],
        "auth_type": row["auth_type"],
        "capabilities": row["capabilities"],
        "node_types": row["node_types"]
    }

@template_generator_agent.tool
async def get_similar_template_structure(ctx: RunContext[WorkflowDependencies], template_id: str) -> Dict:
    """Get the structure of a similar template for reference."""
    template = await ctx.deps.template_service.get_template(template_id)
    
    return {
        "name": template.name,
        "nodes": [node.dict() for node in template.nodes],
        "connections": template.connections
    }

class TemplateAgent:
    """Agent for understanding and generating workflow templates from natural language."""
    
    def __init__(self, db_pool, vector_store_service, template_service):
        """Initialize the template agent."""
        self.db_pool = db_pool
        self.vector_store = vector_store_service
        self.template_service = template_service
        
    async def analyze_template_intent(self, description: str) -> TemplateIntent:
        """Analyze the intent for a workflow template from natural language."""
        async with self.db_pool.acquire() as conn:
            deps = WorkflowDependencies(conn, self.vector_store, self.template_service)
            result = await template_intent_agent.run(description, deps=deps)
            return result.output
    
    async def generate_template(self, intent: TemplateIntent) -> WorkflowTemplate:
        """Generate a workflow template from an intent."""
        async with self.db_pool.acquire() as conn:
            deps = WorkflowDependencies(conn, self.vector_store, self.template_service)
            result = await template_generator_agent.run(intent.dict(), deps=deps)
            return result.output
    
    async def create_template_from_description(self, description: str) -> WorkflowTemplate:
        """Create a workflow template from a natural language description."""
        # First, analyze the intent
        intent = await self.analyze_template_intent(description)
        
        # Then, generate the template
        template = await self.generate_template(intent)
        
        # Save the template
        template_id = await self.template_service.create_template(template)
        
        # Return the complete template
        return await self.template_service.get_template(template_id)
    
    async def find_similar_templates(self, description: str, limit: int = 5) -> List[Dict]:
        """Find similar templates to a description."""
        results = await self.vector_store.search_templates(
            query_text=description,
            limit=limit
        )
        
        templates = []
        for result in results:
            template = await self.template_service.get_template(result.id)
            templates.append({
                "template": template,
                "similarity": result.score
            })
            
        return templates