"""Workflow data models for the Natural Language Workflow Platform."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator, root_validator
import uuid


class WorkflowStep(BaseModel):
    """A single step in a workflow."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=255)
    type: str = Field(regex="^(trigger|action|condition|transform)$")
    service: Optional[str] = Field(None, max_length=100)
    configuration: Dict = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    error_handling: Dict = Field(default_factory=dict)
    
    @validator('name')
    def validate_name(cls, v):
        if not v or v.isspace():
            raise ValueError('Step name cannot be empty or whitespace')
        return v.strip()
    
    @validator('dependencies')
    def validate_dependencies(cls, v):
        if len(v) != len(set(v)):
            raise ValueError('Dependencies must be unique')
        return v
    
    @validator('configuration')
    def validate_configuration(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Configuration must be a dictionary')
        return v


class WorkflowIntent(BaseModel):
    """User intent for workflow creation."""
    
    goal: str = Field(description="Main goal of the workflow", min_length=1, max_length=500)
    input_data: Dict[str, Any] = Field(description="Input data requirements", default_factory=dict)
    expected_output: str = Field(description="Expected output format and content", min_length=1, max_length=500)
    constraints: List[str] = Field(description="Constraints and requirements", default_factory=list)
    integrations: List[str] = Field(description="External services needed", default_factory=list)
    trigger_type: Optional[str] = Field(None, description="What triggers the workflow", max_length=100)
    complexity_score: float = Field(ge=0.0, le=1.0, description="Workflow complexity", default=0.5)
    confidence: float = Field(ge=0.0, le=1.0, description="Parsing confidence", default=1.0)
    
    @validator('goal', 'expected_output')
    def validate_non_empty_strings(cls, v):
        if not v or v.isspace():
            raise ValueError('Field cannot be empty or whitespace')
        return v.strip()
    
    @validator('constraints', 'integrations')
    def validate_string_lists(cls, v):
        if not isinstance(v, list):
            raise ValueError('Field must be a list')
        # Remove duplicates and empty strings
        cleaned = [item.strip() for item in v if item and not item.isspace()]
        return list(set(cleaned))
    
    @validator('input_data')
    def validate_input_data(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Input data must be a dictionary')
        return v
    
    @validator('complexity_score', 'confidence')
    def validate_scores(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError('Score must be between 0.0 and 1.0')
        return v


class ExecutableWorkflow(BaseModel):
    """A complete executable workflow definition."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    steps: List[WorkflowStep] = Field(min_items=1)
    schedule: Optional[str] = Field(None, max_length=100)
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    estimated_runtime: int = Field(gt=0, description="Estimated runtime in seconds")
    
    @validator('name', 'description')
    def validate_non_empty_strings(cls, v):
        if not v or v.isspace():
            raise ValueError('Field cannot be empty or whitespace')
        return v.strip()
    
    @validator('steps')
    def validate_steps(cls, v):
        if not v:
            raise ValueError('Workflow must have at least one step')
        
        # Check for unique step IDs
        step_ids = [step.id for step in v]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError('All step IDs must be unique')
        
        return v
    
    @root_validator
    def validate_workflow_dependencies(cls, values):
        steps = values.get('steps', [])
        if not steps:
            return values
        
        step_ids = {step.id for step in steps}
        
        # Validate all dependencies exist
        for step in steps:
            for dep_id in step.dependencies:
                if dep_id not in step_ids:
                    raise ValueError(f'Step {step.id} depends on non-existent step {dep_id}')
        
        # Check for circular dependencies
        def has_circular_dependency(step_id, visited, rec_stack):
            visited.add(step_id)
            rec_stack.add(step_id)
            
            step = next((s for s in steps if s.id == step_id), None)
            if step:
                for dep_id in step.dependencies:
                    if dep_id not in visited:
                        if has_circular_dependency(dep_id, visited, rec_stack):
                            return True
                    elif dep_id in rec_stack:
                        return True
            
            rec_stack.remove(step_id)
            return False
        
        visited = set()
        for step in steps:
            if step.id not in visited:
                if has_circular_dependency(step.id, visited, set()):
                    raise ValueError('Circular dependency detected in workflow steps')
        
        return values
    
    @validator('schedule')
    def validate_schedule(cls, v):
        if v is not None and v.strip():
            # Basic cron expression validation (5 or 6 fields)
            parts = v.strip().split()
            if len(parts) not in [5, 6]:
                raise ValueError('Schedule must be a valid cron expression')
        return v


class WorkflowContext(BaseModel):
    """Context for workflow execution."""
    
    user_id: str = Field(min_length=1, max_length=255)
    session_id: str = Field(min_length=1, max_length=255)
    current_step: str = Field(min_length=1, max_length=255)
    workflow_data: Dict = Field(default_factory=dict)
    integration_status: Dict[str, str] = Field(default_factory=dict)
    conversation_history: List[Dict] = Field(default_factory=list, max_items=1000)
    
    @validator('user_id', 'session_id', 'current_step')
    def validate_ids(cls, v):
        if not v or v.isspace():
            raise ValueError('ID fields cannot be empty or whitespace')
        return v.strip()
    
    @validator('workflow_data')
    def validate_workflow_data(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Workflow data must be a dictionary')
        return v
    
    @validator('integration_status')
    def validate_integration_status(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Integration status must be a dictionary')
        # Validate status values
        valid_statuses = {'active', 'expired', 'error', 'pending', 'configured'}
        for service, status in v.items():
            if status not in valid_statuses:
                raise ValueError(f'Invalid integration status: {status}')
        return v
    
    @validator('conversation_history')
    def validate_conversation_history(cls, v):
        if not isinstance(v, list):
            raise ValueError('Conversation history must be a list')
        # Validate each conversation entry has required fields
        for entry in v:
            if not isinstance(entry, dict):
                raise ValueError('Each conversation entry must be a dictionary')
            if 'timestamp' not in entry or 'message' not in entry:
                raise ValueError('Each conversation entry must have timestamp and message')
        return v


class WorkflowExecution(BaseModel):
    """Record of a workflow execution."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = Field(min_length=1, max_length=255)
    user_id: str = Field(min_length=1, max_length=255)
    status: str = Field(regex="^(running|completed|failed|cancelled|paused)$")
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    execution_time: Optional[int] = Field(None, ge=0, description="Execution time in seconds")
    step_results: List[Dict] = Field(default_factory=list)
    error_details: Optional[Dict] = None
    
    @validator('workflow_id', 'user_id')
    def validate_ids(cls, v):
        if not v or v.isspace():
            raise ValueError('ID fields cannot be empty or whitespace')
        return v.strip()
    
    @validator('step_results')
    def validate_step_results(cls, v):
        if not isinstance(v, list):
            raise ValueError('Step results must be a list')
        # Validate each step result has required fields
        for result in v:
            if not isinstance(result, dict):
                raise ValueError('Each step result must be a dictionary')
            if 'step_id' not in result or 'status' not in result:
                raise ValueError('Each step result must have step_id and status')
        return v
    
    @validator('error_details')
    def validate_error_details(cls, v):
        if v is not None and not isinstance(v, dict):
            raise ValueError('Error details must be a dictionary')
        return v
    
    @root_validator
    def validate_execution_timing(cls, values):
        started_at = values.get('started_at')
        completed_at = values.get('completed_at')
        status = values.get('status')
        execution_time = values.get('execution_time')
        
        # If completed, must have completed_at timestamp
        if status in ['completed', 'failed', 'cancelled'] and completed_at is None:
            raise ValueError(f'Execution with status {status} must have completed_at timestamp')
        
        # If completed_at is set, it must be after started_at
        if completed_at is not None and started_at is not None:
            if completed_at < started_at:
                raise ValueError('completed_at must be after started_at')
        
        # If execution_time is set and we have both timestamps, validate consistency
        if (execution_time is not None and started_at is not None and 
            completed_at is not None):
            actual_time = int((completed_at - started_at).total_seconds())
            if abs(actual_time - execution_time) > 1:  # Allow 1 second tolerance
                raise ValueError('execution_time must match the difference between timestamps')
        
        return values