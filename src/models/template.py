"""
Workflow template models for the natural language workflow platform.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from uuid import uuid4

class WorkflowNodeConnection(BaseModel):
    """Connection between workflow nodes."""
    source_node_id: str = Field(description="ID of the source node")
    target_node_id: str = Field(description="ID of the target node")
    connection_type: str = Field(description="Type of connection (e.g., 'main', 'ai_tool', 'ai_memory')")
    output_index: int = Field(default=0, description="Output index from source node")
    input_index: int = Field(default=0, description="Input index to target node")

class WorkflowNodePosition(BaseModel):
    """Position of a node in the workflow canvas."""
    x: float = Field(description="X coordinate")
    y: float = Field(description="Y coordinate")

class WorkflowNodeCredential(BaseModel):
    """Credential reference for a workflow node."""
    id: str = Field(description="Credential ID")
    name: str = Field(description="Credential name")

class WorkflowNode(BaseModel):
    """Node in a workflow template."""
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique node identifier")
    name: str = Field(description="Display name of the node")
    type: str = Field(description="Node type identifier")
    position: WorkflowNodePosition = Field(description="Position in the workflow canvas")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Node configuration parameters")
    disabled: bool = Field(default=False, description="Whether the node is disabled")
    credentials: Optional[Dict[str, WorkflowNodeCredential]] = Field(default=None, description="Node credentials")
    type_version: float = Field(default=1.0, description="Version of the node type")

class N8nWorkflowTemplate(BaseModel):
    """Workflow template that can be imported and customized from n8n."""
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique template identifier")
    name: str = Field(description="Template name")
    description: str = Field(description="Template description")
    category: str = Field(description="Template category (e.g., 'Social Media', 'Research', 'Data Processing')")
    tags: List[str] = Field(default_factory=list, description="Template tags for searching")
    nodes: List[WorkflowNode] = Field(default_factory=list, description="Workflow nodes")
    connections: Dict[str, Dict[str, List[Dict[str, Any]]]] = Field(
        default_factory=dict, 
        description="Connections between nodes"
    )
    created_at: datetime = Field(default_factory=datetime.now, description="Template creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Template last update timestamp")
    author_id: Optional[str] = Field(default=None, description="ID of the template author")
    author_name: Optional[str] = Field(default=None, description="Name of the template author")
    version: str = Field(default="1.0.0", description="Template version")
    requirements: Dict[str, str] = Field(
        default_factory=dict, 
        description="Required services and credentials (e.g., {'openai': 'API key', 'telegram': 'Bot token'})"
    )
    setup_instructions: Optional[str] = Field(default=None, description="Instructions for setting up the template")
    example_prompts: List[str] = Field(
        default_factory=list, 
        description="Example natural language prompts that would create this workflow"
    )
    
    # Natural language specific fields
    nl_description: str = Field(description="Natural language description of what the workflow does")
    nl_steps: List[str] = Field(description="Natural language description of workflow steps")
    nl_requirements: List[str] = Field(description="Natural language description of requirements")
    
    @validator('updated_at', pre=True, always=True)
    def set_updated_at(cls, v, values):
        """Set updated_at to current time when the model is updated."""
        return datetime.now()

class N8nTemplateSearchResult(BaseModel):
    """Search result for n8n workflow templates."""
    template_id: str = Field(description="Template ID")
    name: str = Field(description="Template name")
    description: str = Field(description="Template description")
    category: str = Field(description="Template category")
    tags: List[str] = Field(description="Template tags")
    similarity_score: float = Field(description="Similarity score to search query")
    author_name: Optional[str] = Field(default=None, description="Name of the template author")
    
class N8nTemplateImport(BaseModel):
    """Import request for an n8n workflow template."""
    template_id: str = Field(description="Template ID to import")
    user_id: str = Field(description="User ID importing the template")
    customizations: Optional[Dict[str, Any]] = Field(default=None, description="Template customizations")
    
class N8nTemplateExport(BaseModel):
    """Export request for a workflow to n8n format."""
    workflow_id: str = Field(description="Workflow ID to export as template")
    name: str = Field(description="Template name")
    description: str = Field(description="Template description")
    category: str = Field(description="Template category")
    tags: List[str] = Field(default_factory=list, description="Template tags")
    make_public: bool = Field(default=False, description="Whether to make the template public")
    nl_description: str = Field(description="Natural language description of what the workflow does")
    nl_steps: List[str] = Field(description="Natural language description of workflow steps")
    nl_requirements: List[str] = Field(description="Natural language description of requirements")
    example_prompts: List[str] = Field(
        default_factory=list, 
        description="Example natural language prompts that would create this workflow"
    )