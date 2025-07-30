"""Integration management system for the Natural Language Workflow Platform."""

from .registry import IntegrationRegistry, IntegrationDefinition
from .manager import IntegrationManager
from .auth import AuthenticationManager, OAuthHandler, APIKeyHandler
from .clients import BaseAPIClient, HTTPClient
from .config import IntegrationConfig, ServiceCapability

__all__ = [
    "IntegrationRegistry",
    "IntegrationDefinition", 
    "IntegrationManager",
    "AuthenticationManager",
    "OAuthHandler",
    "APIKeyHandler",
    "BaseAPIClient",
    "HTTPClient",
    "IntegrationConfig",
    "ServiceCapability"
]