"""Community and sharing models for the Natural Language Workflow Platform."""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime
import uuid


class TemplateVisibility(str, Enum):
    """Visibility levels for workflow templates."""
    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


class TemplateCategory(str, Enum):
    """Categories for workflow templates."""
    AUTOMATION = "automation"
    DATA_PROCESSING = "data_processing"
    COMMUNICATION = "communication"
    CONTENT_CREATION = "content_creation"
    ANALYTICS = "analytics"
    INTEGRATION = "integration"
    PRODUCTIVITY = "productivity"
    MARKETING = "marketing"
    DEVELOPMENT = "development"
    OTHER = "other"


class TemplateStatus(str, Enum):
    """Status of a workflow template."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    UNDER_REVIEW = "under_review"
    REJECTED = "rejected"


class WorkflowTemplate(BaseModel):
    """A workflow template that can be shared and reused."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    description: str = Field(..., min_length=1, max_length=1000, description="Template description")
    
    # Template content
    template_data: Dict[str, Any] = Field(..., description="Workflow template data")
    variables: Dict[str, Any] = Field(default_factory=dict, description="Template variables")
    
    # Metadata
    category: TemplateCategory = Field(..., description="Template category")
    tags: List[str] = Field(default_factory=list, description="Template tags")
    
    # Authorship and ownership
    created_by: str = Field(..., description="User ID of the creator")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Visibility and status
    visibility: TemplateVisibility = Field(default=TemplateVisibility.PRIVATE)
    status: TemplateStatus = Field(default=TemplateStatus.DRAFT)
    
    # Community metrics
    usage_count: int = Field(default=0, description="Number of times used")
    rating: float = Field(default=0.0, ge=0.0, le=5.0, description="Average rating")
    rating_count: int = Field(default=0, description="Number of ratings")
    
    # Requirements and compatibility
    required_integrations: List[str] = Field(default_factory=list, description="Required integrations")
    estimated_runtime: int = Field(default=300, description="Estimated runtime in seconds")
    complexity_level: str = Field(default="medium", regex="^(beginner|medium|advanced)$")
    
    @validator('tags')
    def validate_tags(cls, v):
        # Remove duplicates and empty tags
        return list(set([tag.strip().lower() for tag in v if tag.strip()]))
    
    @validator('name', 'description')
    def validate_non_empty_strings(cls, v):
        if not v or v.isspace():
            raise ValueError('Field cannot be empty or whitespace')
        return v.strip()


class TemplateRating(BaseModel):
    """A rating for a workflow template."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str = Field(..., description="Template being rated")
    user_id: str = Field(..., description="User who gave the rating")
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    review: Optional[str] = Field(None, max_length=1000, description="Optional review text")
    created_at: datetime = Field(default_factory=datetime.now)
    
    @validator('review')
    def validate_review(cls, v):
        if v is not None:
            v = v.strip()
            return v if v else None
        return v


class TemplateUsage(BaseModel):
    """Record of template usage."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str = Field(..., description="Template that was used")
    user_id: str = Field(..., description="User who used the template")
    workflow_id: Optional[str] = Field(None, description="Created workflow ID")
    used_at: datetime = Field(default_factory=datetime.now)
    customizations: Dict[str, Any] = Field(default_factory=dict, description="User customizations")


class TemplateComment(BaseModel):
    """A comment on a workflow template."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str = Field(..., description="Template being commented on")
    user_id: str = Field(..., description="User who made the comment")
    content: str = Field(..., min_length=1, max_length=1000, description="Comment content")
    parent_id: Optional[str] = Field(None, description="Parent comment ID for replies")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(None)
    
    @validator('content')
    def validate_content(cls, v):
        if not v or v.isspace():
            raise ValueError('Comment content cannot be empty')
        return v.strip()


class TemplateCollection(BaseModel):
    """A collection of workflow templates."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=255, description="Collection name")
    description: str = Field(..., min_length=1, max_length=1000, description="Collection description")
    
    # Ownership
    created_by: str = Field(..., description="User ID of the creator")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # Content
    template_ids: List[str] = Field(default_factory=list, description="Template IDs in this collection")
    
    # Visibility
    visibility: TemplateVisibility = Field(default=TemplateVisibility.PRIVATE)
    
    # Metadata
    tags: List[str] = Field(default_factory=list, description="Collection tags")
    
    @validator('name', 'description')
    def validate_non_empty_strings(cls, v):
        if not v or v.isspace():
            raise ValueError('Field cannot be empty or whitespace')
        return v.strip()


class TemplateSearchQuery(BaseModel):
    """Query for searching workflow templates."""
    
    query: Optional[str] = Field(None, description="Text search query")
    category: Optional[TemplateCategory] = Field(None, description="Filter by category")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    required_integrations: Optional[List[str]] = Field(None, description="Filter by required integrations")
    complexity_level: Optional[str] = Field(None, regex="^(beginner|medium|advanced)$")
    min_rating: Optional[float] = Field(None, ge=0.0, le=5.0, description="Minimum rating")
    visibility: Optional[TemplateVisibility] = Field(None, description="Filter by visibility")
    created_by: Optional[str] = Field(None, description="Filter by creator")
    
    # Sorting
    sort_by: str = Field("created_at", regex="^(created_at|updated_at|rating|usage_count|name)$")
    sort_order: str = Field("desc", regex="^(asc|desc)$")
    
    # Pagination
    limit: int = Field(20, ge=1, le=100, description="Number of results to return")
    offset: int = Field(0, ge=0, description="Number of results to skip")


class TemplateSearchResult(BaseModel):
    """Result from template search."""
    
    templates: List[WorkflowTemplate] = Field(..., description="Found templates")
    total_count: int = Field(..., description="Total number of matching templates")
    has_more: bool = Field(..., description="Whether there are more results")
    facets: Dict[str, Any] = Field(default_factory=dict, description="Search facets")


class TemplateAdaptationRequest(BaseModel):
    """Request to adapt a template for a user."""
    
    template_id: str = Field(..., description="Template to adapt")
    customizations: Dict[str, Any] = Field(default_factory=dict, description="User customizations")
    name: Optional[str] = Field(None, description="Custom name for the adapted workflow")
    description: Optional[str] = Field(None, description="Custom description")


class TemplateAdaptationResult(BaseModel):
    """Result of template adaptation."""
    
    workflow_id: str = Field(..., description="ID of the created workflow")
    template_id: str = Field(..., description="Original template ID")
    customizations_applied: Dict[str, Any] = Field(..., description="Applied customizations")
    success: bool = Field(..., description="Whether adaptation was successful")
    message: str = Field(..., description="Result message")


class CommunityStats(BaseModel):
    """Community statistics."""
    
    total_templates: int = Field(..., description="Total number of public templates")
    total_users: int = Field(..., description="Total number of contributing users")
    total_usage: int = Field(..., description="Total template usage count")
    popular_categories: List[Dict[str, Any]] = Field(..., description="Popular template categories")
    top_contributors: List[Dict[str, Any]] = Field(..., description="Top contributing users")
    recent_templates: List[WorkflowTemplate] = Field(..., description="Recently published templates")


class ModerationAction(str, Enum):
    """Moderation actions for community content."""
    APPROVE = "approve"
    REJECT = "reject"
    FLAG = "flag"
    UNFLAG = "unflag"
    ARCHIVE = "archive"
    DELETE = "delete"


class ModerationRequest(BaseModel):
    """Request for content moderation."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content_type: str = Field(..., regex="^(template|comment|rating)$")
    content_id: str = Field(..., description="ID of the content to moderate")
    action: ModerationAction = Field(..., description="Moderation action to take")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the action")
    moderator_id: str = Field(..., description="ID of the moderator")
    created_at: datetime = Field(default_factory=datetime.now)
    
    @validator('reason')
    def validate_reason(cls, v):
        if not v or v.isspace():
            raise ValueError('Reason cannot be empty')
        return v.strip()