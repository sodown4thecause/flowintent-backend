"""API endpoints for natural language workflow creation and execution."""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from ..services.vector_store import VectorStoreService, get_vector_store
from ..services.workflow_service import WorkflowService, get_workflow_service
from ..services.template_service import TemplateService
from ..dependencies import get_current_user
from ..models.user import User
from ..models.workflow import WorkflowIntent, ExecutableWorkflow
from ..models.template import WorkflowTemplateSearchResult, WorkflowTemplateImport
from ..agents.intent_parser import parse_intent, IntentParsingResult
from ..agents.workflow_builder import build_workflow, WorkflowBuildResult
from ..agents.orchestrator import handle_user_input, PlatformState
from ..agents.template_agent import TemplateAgent
from ..agents.workflow_agent import WorkflowAgentService, WorkflowRequest, WorkflowResponse


router = APIRouter(prefix="/nl-workflows", tags=["natural-language-workflows"])


class NLWorkflowRequest(BaseModel):
    """Request model for natural language workflow creation."""
    description: str = Field(..., description="Natural language description of the workflow")
    user_preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences")


class NLWorkflowResponse(BaseModel):
    """Response model for natural language workflow creation."""
    workflow_id: Optional[str] = None
    execution_id: Optional[str] = None
    status: str
    message: str
    requires_clarification: bool = False
    clarification_questions: List[str] = Field(default_factory=list)
    workflow_details: Optional[Dict[str, Any]] = None


@router.post("/create", response_model=NLWorkflowResponse)
async def create_nl_workflow(
    request: NLWorkflowRequest,
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Create a workflow from natural language description."""
    try:
        # Parse the intent
        intent_result = await parse_intent(
            user_input=request.description,
            vector_store=vector_store,
            user_id=str(current_user.id),
            user_preferences=request.user_preferences
        )
        
        # Check if clarification is needed
        if intent_result.requires_clarification:
            return NLWorkflowResponse(
                status="clarification_needed",
                message="Please provide more information to create the workflow",
                requires_clarification=True,
                clarification_questions=intent_result.clarification_questions
            )
        
        # Build the workflow
        workflow_result = await build_workflow(
            intent=intent_result.intent,
            vector_store=vector_store,
            user_id=str(current_user.id)
        )
        
        # Return the workflow details without executing
        return NLWorkflowResponse(
            workflow_id=workflow_result.workflow.id,
            status="created",
            message="Workflow created successfully",
            workflow_details=workflow_result.workflow.dict()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.post("/execute", response_model=NLWorkflowResponse)
async def execute_nl_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Execute a previously created workflow."""
    try:
        # Get the workflow
        workflow = await workflow_service.get_workflow(workflow_id, str(current_user.id))
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Execute the workflow
        execution_id = await workflow_service.execute_workflow(
            workflow=workflow,
            user_id=str(current_user.id)
        )
        
        return NLWorkflowResponse(
            workflow_id=workflow_id,
            execution_id=execution_id,
            status="executing",
            message="Workflow execution started"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute workflow: {str(e)}")


@router.post("/conversation", response_model=Dict[str, Any])
async def process_conversation(
    user_input: str,
    conversation_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store),
    workflow_service: WorkflowService = Depends(get_workflow_service)
):
    """Process a conversation message and manage workflow creation/execution."""
    try:
        # Initialize or retrieve platform state
        state = PlatformState(
            user_id=str(current_user.id),
            conversation_id=conversation_id or ""
        )
        
        # Handle the user input
        result = await handle_user_input(
            user_input=user_input,
            state=state,
            vector_store=vector_store,
            workflow_service=workflow_service
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process conversation: {str(e)}")


@router.get("/similar", response_model=List[Dict[str, Any]])
async def find_similar_workflows(
    query: str,
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    vector_store: VectorStoreService = Depends(get_vector_store)
):
    """Find similar workflows based on natural language query."""
    try:
        results = await vector_store.search(
            query=query,
            collection_type="workflows",
            limit=limit,
            threshold=0.6
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to find similar workflows: {str(e)}")
# Add dependencies for template service and agents
from ..dependencies import get_db_pool
def get_template_service(
    db_pool=Depends(get_db_pool),
    vector_store=Depends(get_vector_store)
):
    """Get template service dependency."""
    return TemplateService(db_pool, vector_store)

def get_template_agent(
    db_pool=Depends(get_db_pool),
    vector_store=Depends(get_vector_store),
    template_service=Depends(get_template_service)
):
    """Get template agent dependency."""
    return TemplateAgent(db_pool, vector_store, template_service)

def get_workflow_agent_service(
    db_pool=Depends(get_db_pool),
    vector_store=Depends(get_vector_store),
    template_service=Depends(get_template_service),
    template_agent=Depends(get_template_agent)
):
    """Get workflow agent service dependency."""
    return WorkflowAgentService(db_pool, vector_store, template_service, template_agent)


class TemplateBasedWorkflowRequest(BaseModel):
    """Request model for template-based workflow creation."""
    description: str = Field(..., description="Natural language description of the workflow")
    use_templates: bool = Field(default=True, description="Whether to use templates for workflow creation")
    template_id: Optional[str] = Field(default=None, description="Specific template ID to use (optional)")
    customizations: Optional[Dict[str, Any]] = Field(default=None, description="Template customizations")


@router.post("/template-based", response_model=WorkflowResponse)
async def create_template_based_workflow(
    request: TemplateBasedWorkflowRequest,
    current_user: User = Depends(get_current_user),
    workflow_agent_service: WorkflowAgentService = Depends(get_workflow_agent_service)
):
    """Create a workflow using templates and natural language."""
    try:
        # Create workflow request
        workflow_request = WorkflowRequest(
            description=request.description,
            user_id=str(current_user.id),
            context={
                "use_templates": request.use_templates,
                "template_id": request.template_id,
                "customizations": request.customizations
            }
        )
        
        # Process the request
        response = await workflow_agent_service.process_workflow_request(workflow_request)
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create workflow: {str(e)}")


@router.get("/templates/search", response_model=List[WorkflowTemplateSearchResult])
async def search_workflow_templates(
    query: str,
    category: Optional[str] = None,
    limit: int = 10,
    template_service: TemplateService = Depends(get_template_service)
):
    """Search for workflow templates using natural language."""
    try:
        results = await template_service.search_templates(
            query=query,
            category=category,
            limit=limit
        )
        
        return results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search templates: {str(e)}")


@router.post("/templates/import", response_model=Dict[str, Any])
async def import_workflow_template(
    import_request: WorkflowTemplateImport,
    current_user: User = Depends(get_current_user),
    template_service: TemplateService = Depends(get_template_service)
):
    """Import a workflow template for the current user."""
    try:
        # Set the user ID from the current user
        import_request.user_id = str(current_user.id)
        
        # Import the template
        result = await template_service.import_template(import_request)
        
        return result
        
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import template: {str(e)}")