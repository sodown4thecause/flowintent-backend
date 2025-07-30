"""User data models for the Natural Language Workflow Platform."""

from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field, EmailStr, validator
import uuid


class User(BaseModel):
    """User account information."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    preferences: Dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    subscription_tier: str = Field(default="free", regex="^(free|pro|enterprise)$")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or v.isspace():
            raise ValueError('Name cannot be empty or whitespace')
        return v.strip()
    
    @validator('preferences')
    def validate_preferences(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Preferences must be a dictionary')
        return v


class Session(BaseModel):
    """User session information."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(min_length=1, max_length=255)
    created_at: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    status: str = Field(default="active", regex="^(active|expired|terminated)$")
    
    @validator('user_id')
    def validate_user_id(cls, v):
        if not v or v.isspace():
            raise ValueError('User ID cannot be empty or whitespace')
        return v.strip()
    
    @validator('last_activity')
    def validate_last_activity(cls, v, values):
        created_at = values.get('created_at')
        if created_at and v < created_at:
            raise ValueError('Last activity cannot be before creation time')
        return v


class UserIntegration(BaseModel):
    """User integration with external service."""
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = Field(min_length=1, max_length=255)
    service_name: str = Field(min_length=1, max_length=100)
    auth_data: Dict = Field(description="Encrypted authentication data")
    configuration: Dict = Field(default_factory=dict)
    status: str = Field(default="active", regex="^(active|expired|error|pending)$")
    created_at: datetime = Field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    
    @validator('user_id', 'service_name')
    def validate_non_empty_strings(cls, v):
        if not v or v.isspace():
            raise ValueError('Field cannot be empty or whitespace')
        return v.strip()
    
    @validator('auth_data')
    def validate_auth_data(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Auth data must be a dictionary')
        if not v:
            raise ValueError('Auth data cannot be empty')
        return v
    
    @validator('configuration')
    def validate_configuration(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Configuration must be a dictionary')
        return v
    
    @validator('last_used')
    def validate_last_used(cls, v, values):
        if v is not None:
            created_at = values.get('created_at')
            if created_at and v < created_at:
                raise ValueError('Last used cannot be before creation time')
        return v