"""Integration models for the Natural Language Workflow Platform."""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime

from src.integrations.config import AuthType, ServiceCapability


class IntegrationStatus(str, Enum):
    """Status of an integration."""
    AVAILABLE = "available"
    CONFIGURED = "configured"
    AUTHENTICATING = "authenticating"
    ERROR = "error"
    DISABLED = "disabled"


class IntegrationConfig(BaseModel):
    """Configuration for setting up an integration."""
    service_name: str = Field(..., description="Name of the service to integrate")
    auth_type: AuthType = Field(..., description="Authentication method")
    credentials: Dict[str, Any] = Field(..., description="Authentication credentials")
    custom_config: Dict[str, Any] = Field(default_factory=dict, description="Custom configuration")
    enabled: bool = Field(True, description="Whether the integration is enabled")
    
    @validator('service_name')
    def validate_service_name(cls, v):
        if not v or not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Service name must be alphanumeric with underscores or hyphens')
        return v.lower()


class IntegrationTestResult(BaseModel):
    """Result of testing an integration."""
    service_name: str = Field(..., description="Name of the service")
    success: bool = Field(..., description="Whether the test was successful")
    message: str = Field(..., description="Test result message")
    response_time: Optional[float] = Field(None, description="Response time in seconds")
    capabilities_verified: List[ServiceCapability] = Field(default_factory=list, description="Verified capabilities")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Error details if test failed")


class ServiceDiscoveryResult(BaseModel):
    """Result of service discovery."""
    service_name: str = Field(..., description="Name of the service")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Service description")
    auth_type: AuthType = Field(..., description="Required authentication type")
    capabilities: List[ServiceCapability] = Field(..., description="Service capabilities")
    status: IntegrationStatus = Field(..., description="Current status")
    configuration_required: bool = Field(..., description="Whether configuration is required")
    health_status: str = Field("unknown", description="Health status")


class IntegrationOperation(BaseModel):
    """Request to perform an operation on an integration."""
    service_name: str = Field(..., description="Name of the service")
    operation: str = Field(..., description="Operation to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Operation parameters")
    timeout: Optional[int] = Field(30, description="Operation timeout in seconds")


class IntegrationOperationResult(BaseModel):
    """Result of an integration operation."""
    service_name: str = Field(..., description="Name of the service")
    operation: str = Field(..., description="Operation that was performed")
    success: bool = Field(..., description="Whether the operation was successful")
    result: Optional[Any] = Field(None, description="Operation result data")
    error_message: Optional[str] = Field(None, description="Error message if operation failed")
    execution_time: float = Field(..., description="Execution time in seconds")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the operation was performed")


class AuthenticationFlow(BaseModel):
    """Authentication flow information."""
    service_name: str = Field(..., description="Name of the service")
    auth_type: AuthType = Field(..., description="Authentication type")
    flow_id: str = Field(..., description="Unique flow identifier")
    authorization_url: Optional[str] = Field(None, description="OAuth authorization URL")
    required_fields: List[str] = Field(default_factory=list, description="Required credential fields")
    instructions: str = Field(..., description="Instructions for the user")
    expires_at: Optional[datetime] = Field(None, description="When the flow expires")


class IntegrationHealth(BaseModel):
    """Health status of an integration."""
    service_name: str = Field(..., description="Name of the service")
    status: str = Field(..., description="Health status")
    last_check: datetime = Field(..., description="Last health check time")
    response_time: Optional[float] = Field(None, description="Last response time")
    error_count: int = Field(0, description="Number of recent errors")
    last_error: Optional[str] = Field(None, description="Last error message")
    uptime_percentage: float = Field(100.0, description="Uptime percentage")


class IntegrationCapabilityCheck(BaseModel):
    """Check if a service supports specific capabilities."""
    service_name: str = Field(..., description="Name of the service")
    required_capabilities: List[ServiceCapability] = Field(..., description="Required capabilities")
    
    
class IntegrationCapabilityResult(BaseModel):
    """Result of capability check."""
    service_name: str = Field(..., description="Name of the service")
    supported_capabilities: List[ServiceCapability] = Field(..., description="Supported capabilities")
    missing_capabilities: List[ServiceCapability] = Field(..., description="Missing capabilities")
    is_compatible: bool = Field(..., description="Whether all required capabilities are supported")
    alternative_services: List[str] = Field(default_factory=list, description="Alternative services with required capabilities")