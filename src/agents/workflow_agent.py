"""
Agent for natural language workflow creation and management.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.models.template import WorkflowTemplate
from src.agents.template_agent import TemplateIntent

class WorkflowRequest(BaseModel):
    """User request for workflow creation or management."""
    description: str = Field(description="Natural language description of the workflow request")
    user_id: str = Field(description="ID of the user making the request")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context for the request")

class WorkflowResponse(BaseModel):
    """Response to a workflow request."""
    message: str = Field(description="Response message to the user")
    workflow_id: Optional[str] = Field(default=None, description="ID of the created or modified workflow")
    template_id: Optional[str] = Field(default=None, description="ID of the template used or created")
    next_steps: List[str] = Field(default_factory=list, description="Suggested next steps for the user")
    clarification_questions: List[str] = Field(default_factory=list, description="Questions to clarify the request")

class WorkflowDependencies:
    """Dependencies for workflow agent."""
    def __init__(self, db_conn, vector_store, template_service, template_agent):
        self.db_conn = db_conn
        self.vector_store = vector_store
        self.template_service = template_service
        self.template_agent = template_agent

workflow_agent = Agent[WorkflowDependencies, WorkflowResponse](
    model='openai:gpt-4o',
    deps_type=WorkflowDependencies,
    output_type=WorkflowResponse,
    system_prompt="""
    You are a workflow creation assistant for a natural language workflow platform.
    Your job is to understand user requests for creating or managing workflows and
    respond with helpful information and next steps.
    
    You can:
    1. Help users create new workflows based on their descriptions
    2. Find similar workflow templates that match their needs
    3. Suggest modifications to existing workflows
    4. Ask clarifying questions when needed
    
    Always be helpful, clear, and focused on the user's workflow automation needs.
    """
)

@workflow_agent.tool
async def analyze_workflow_intent(ctx: RunContext[WorkflowDependencies], description: str) -> Dict:
    """Analyze the intent for a workflow from natural language."""
    intent = await ctx.deps.template_agent.analyze_template_intent(description)
    return intent.dict()

@workflow_agent.tool
async def find_similar_templates(ctx: RunContext[WorkflowDependencies], description: str) -> List[Dict]:
    """Find similar workflow templates to a description."""
    results = await ctx.deps.template_service.search_templates(query=description, limit=5)
    return [result.dict() for result in results]

@workflow_agent.tool
async def get_template_details(ctx: RunContext[WorkflowDependencies], template_id: str) -> Dict:
    """Get details about a workflow template."""
    template = await ctx.deps.template_service.get_template(template_id)
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "tags": template.tags,
        "nl_description": template.nl_description,
        "nl_steps": template.nl_steps,
        "nl_requirements": template.nl_requirements,
        "example_prompts": template.example_prompts
    }

@workflow_agent.tool
async def create_workflow_from_template(
    ctx: RunContext[WorkflowDependencies], 
    template_id: str, 
    user_id: str,
    customizations: Optional[Dict[str, Any]] = None
) -> Dict:
    """Create a workflow from a template."""
    from src.models.template import WorkflowTemplateImport
    
    import_request = WorkflowTemplateImport(
        template_id=template_id,
        user_id=user_id,
        customizations=customizations
    )
    
    result = await ctx.deps.template_service.import_template(import_request)
    return result

@workflow_agent.tool
async def create_custom_workflow(
    ctx: RunContext[WorkflowDependencies],
    description: str,
    user_id: str
) -> Dict:
    """Create a custom workflow from a description."""
    # First create a template
    template = await ctx.deps.template_agent.create_template_from_description(description)
    
    # Then create a workflow from the template
    from src.models.template import WorkflowTemplateImport
    
    import_request = WorkflowTemplateImport(
        template_id=template.id,
        user_id=user_id
    )
    
    result = await ctx.deps.template_service.import_template(import_request)
    
    return {
        "workflow_id": result["workflow_id"],
        "template_id": template.id,
        "name": result["name"],
        "message": result["message"]
    }

class WorkflowAgentService:
    """Service for natural language workflow creation and management."""
    
    def __init__(self, db_pool, vector_store_service, template_service, template_agent):
        """Initialize the workflow agent service."""
        self.db_pool = db_pool
        self.vector_store = vector_store_service
        self.template_service = template_service
        self.template_agent = template_agent
        
    async def process_workflow_request(self, request: WorkflowRequest) -> WorkflowResponse:
        """Process a natural language workflow request."""
        async with self.db_pool.acquire() as conn:
            deps = WorkflowDependencies(
                conn, 
                self.vector_store, 
                self.template_service,
                self.template_agent
            )
            
            result = await workflow_agent.run(request.dict(), deps=deps)
            return result.output