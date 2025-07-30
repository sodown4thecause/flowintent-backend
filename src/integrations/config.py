"""Configuration models for integrations."""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class AuthType(str, Enum):
    """Authentication types for integrations."""
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC_AUTH = "basic_auth"
    BEARER_TOKEN = "bearer_token"
    CUSTOM = "custom"


class ServiceCapability(str, Enum):
    """Capabilities that services can provide."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    SEARCH = "search"
    WEBHOOK = "webhook"
    REAL_TIME = "real_time"
    BATCH = "batch"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    requests_per_day: Optional[int] = None
    burst_limit: Optional[int] = None
    backoff_factor: float = 1.5
    max_retry_delay: int = 300  # seconds


class IntegrationConfig(BaseModel):
    """Configuration for an integration."""
    
    service_name: str = Field(..., description="Name of the service")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Description of the service")
    
    # Authentication
    auth_type: AuthType = Field(..., description="Authentication method")
    auth_config: Dict[str, Any] = Field(default_factory=dict, description="Auth-specific configuration")
    
    # API Configuration
    base_url: str = Field(..., description="Base URL for the API")
    api_version: Optional[str] = Field(None, description="API version")
    
    # Capabilities
    capabilities: List[ServiceCapability] = Field(default_factory=list, description="Service capabilities")
    
    # Rate limiting
    rate_limit: Optional[RateLimitConfig] = Field(None, description="Rate limiting configuration")
    
    # Headers and configuration
    default_headers: Dict[str, str] = Field(default_factory=dict, description="Default HTTP headers")
    timeout: int = Field(30, description="Request timeout in seconds")
    
    # Webhook configuration
    webhook_url: Optional[str] = Field(None, description="Webhook endpoint URL")
    webhook_secret: Optional[str] = Field(None, description="Webhook secret for verification")
    
    # Service-specific configuration
    custom_config: Dict[str, Any] = Field(default_factory=dict, description="Service-specific settings")
    
    # Status
    enabled: bool = Field(True, description="Whether the integration is enabled")
    health_check_url: Optional[str] = Field(None, description="URL for health checks")
    
    @validator('service_name')
    def validate_service_name(cls, v):
        if not v or not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Service name must be alphanumeric with underscores or hyphens')
        return v.lower()
    
    @validator('base_url')
    def validate_base_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Base URL must start with http:// or https://')
        return v.rstrip('/')


class OAuthConfig(BaseModel):
    """OAuth 2.0 configuration."""
    
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    
    # URLs
    authorization_url: str = Field(..., description="Authorization endpoint")
    token_url: str = Field(..., description="Token endpoint")
    refresh_url: Optional[str] = Field(None, description="Token refresh endpoint")
    revoke_url: Optional[str] = Field(None, description="Token revocation endpoint")
    
    # Scopes and parameters
    scopes: List[str] = Field(default_factory=list, description="Required OAuth scopes")
    redirect_uri: str = Field(..., description="Redirect URI after authorization")
    
    # Token configuration
    token_type: str = Field("Bearer", description="Token type")
    access_token_expires: Optional[int] = Field(None, description="Access token expiry in seconds")
    refresh_token_expires: Optional[int] = Field(None, description="Refresh token expiry in seconds")
    
    # Additional parameters
    additional_params: Dict[str, str] = Field(default_factory=dict, description="Additional OAuth parameters")


class APIKeyConfig(BaseModel):
    """API Key authentication configuration."""
    
    key_name: str = Field(..., description="Name of the API key parameter")
    key_location: str = Field("header", description="Where to send the key: header, query, or body")
    key_prefix: Optional[str] = Field(None, description="Prefix for the API key (e.g., 'Bearer ')")
    
    @validator('key_location')
    def validate_key_location(cls, v):
        if v not in ['header', 'query', 'body']:
            raise ValueError('Key location must be header, query, or body')
        return v


class BasicAuthConfig(BaseModel):
    """Basic authentication configuration."""
    
    username_field: str = Field("username", description="Username field name")
    password_field: str = Field("password", description="Password field name")


class WebhookConfig(BaseModel):
    """Webhook configuration for a service."""
    
    url: str = Field(..., description="Webhook endpoint URL")
    secret: Optional[str] = Field(None, description="Webhook secret for verification")
    events: List[str] = Field(default_factory=list, description="Events to subscribe to")
    headers: Dict[str, str] = Field(default_factory=dict, description="Custom headers")
    
    # Verification
    signature_header: Optional[str] = Field(None, description="Header containing signature")
    signature_algorithm: str = Field("sha256", description="Signature algorithm")
    
    # Retry configuration
    retry_attempts: int = Field(3, description="Number of retry attempts")
    retry_delay: int = Field(5, description="Delay between retries in seconds")


# Predefined integration configurations
PREDEFINED_INTEGRATIONS = {
    "openai": IntegrationConfig(
        service_name="openai",
        display_name="OpenAI",
        description="OpenAI API for AI models and completions",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.openai.com/v1",
        capabilities=[ServiceCapability.READ, ServiceCapability.WRITE],
        auth_config={
            "token_header": "Authorization",
            "token_prefix": "Bearer "
        },
        rate_limit=RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=3600
        )
    ),
    
    "google_drive": IntegrationConfig(
        service_name="google_drive",
        display_name="Google Drive",
        description="Google Drive API for file storage and management",
        auth_type=AuthType.OAUTH2,
        base_url="https://www.googleapis.com/drive/v3",
        capabilities=[
            ServiceCapability.READ,
            ServiceCapability.WRITE,
            ServiceCapability.DELETE,
            ServiceCapability.LIST,
            ServiceCapability.SEARCH,
            ServiceCapability.FILE_UPLOAD,
            ServiceCapability.FILE_DOWNLOAD
        ],
        auth_config={
            "authorization_url": "https://accounts.google.com/o/oauth2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "scopes": [
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/drive.file"
            ]
        }
    ),
    
    "slack": IntegrationConfig(
        service_name="slack",
        display_name="Slack",
        description="Slack API for messaging and workspace management",
        auth_type=AuthType.OAUTH2,
        base_url="https://slack.com/api",
        capabilities=[
            ServiceCapability.READ,
            ServiceCapability.WRITE,
            ServiceCapability.WEBHOOK,
            ServiceCapability.REAL_TIME
        ],
        auth_config={
            "authorization_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "scopes": ["chat:write", "channels:read", "users:read"]
        },
        webhook_url="/webhooks/slack"
    ),
    
    "github": IntegrationConfig(
        service_name="github",
        display_name="GitHub",
        description="GitHub API for repository and issue management",
        auth_type=AuthType.BEARER_TOKEN,
        base_url="https://api.github.com",
        capabilities=[
            ServiceCapability.READ,
            ServiceCapability.WRITE,
            ServiceCapability.DELETE,
            ServiceCapability.WEBHOOK
        ],
        auth_config={
            "token_header": "Authorization",
            "token_prefix": "token "
        },
        rate_limit=RateLimitConfig(
            requests_per_hour=5000
        )
    )
}