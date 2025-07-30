"""Integration Agent for external service management."""

import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from dataclasses import dataclass

from src.models.integration import (
    IntegrationConfig,
    IntegrationTestResult,
    ServiceDiscoveryResult,
    IntegrationOperation,
    IntegrationOperationResult,
    AuthenticationFlow,
    IntegrationHealth,
    IntegrationCapabilityCheck,
    IntegrationCapabilityResult,
    IntegrationStatus
)
from src.integrations.manager import IntegrationManager, integration_manager
from src.integrations.registry import IntegrationRegistry, integration_registry
from src.integrations.config import AuthType, ServiceCapability
from src.integrations.auth import AuthenticationManager, OAuthHandler, APIKeyHandler
from src.errors import IntegrationError, handle_errors
from src.services.database import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class IntegrationAgentDeps:
    """Dependencies for the Integration Agent."""
    integration_manager: IntegrationManager
    integration_registry: IntegrationRegistry
    user_id: str
    db: Optional[DatabaseService] = None


class IntegrationAgentResult(BaseModel):
    """Result from the Integration Agent."""
    action: str = Field(description="Action that was performed")
    success: bool = Field(description="Whether the action was successful")
    message: str = Field(description="Human-readable message about the result")
    data: Optional[Any] = Field(None, description="Result data")
    next_steps: List[str] = Field(default_factory=list, description="Suggested next steps")
    requires_user_action: bool = Field(False, description="Whether user action is required")


# Create the Integration Agent
integration_agent = Agent[IntegrationAgentDeps, IntegrationAgentResult](
    model='openai:gpt-4o',
    deps_type=IntegrationAgentDeps,
    output_type=IntegrationAgentResult,
    system_prompt="""
    You are an Integration Agent for a Natural Language Workflow Platform.
    Your job is to help users discover, configure, and manage integrations with external services.
    
    You can:
    1. Discover available services and their capabilities
    2. Help users authenticate with services (OAuth2, API keys, etc.)
    3. Test service connections and validate configurations
    4. Perform operations on integrated services
    5. Monitor service health and handle authentication issues
    6. Suggest alternative services when needed
    
    Always provide clear, helpful guidance and handle errors gracefully.
    Focus on making integrations as seamless as possible for users.
    """
)


@integration_agent.tool
async def discover_services(
    ctx: RunContext[IntegrationAgentDeps],
    query: Optional[str] = None,
    capabilities: Optional[List[str]] = None
) -> List[ServiceDiscoveryResult]:
    """Discover available services based on query or capabilities."""
    try:
        # Convert string capabilities to ServiceCapability enum
        capability_filters = []
        if capabilities:
            for cap in capabilities:
                try:
                    capability_filters.append(ServiceCapability(cap))
                except ValueError:
                    logger.warning(f"Invalid capability: {cap}")
        
        if query:
            # Search by query
            definitions = ctx.deps.integration_registry.search_integrations(
                query=query,
                capabilities=capability_filters if capability_filters else None
            )
        elif capability_filters:
            # Filter by capabilities
            definitions = []
            for cap in capability_filters:
                definitions.extend(
                    ctx.deps.integration_registry.get_integrations_by_capability(cap)
                )
            # Remove duplicates
            seen = set()
            unique_definitions = []
            for d in definitions:
                if d.service_name not in seen:
                    unique_definitions.append(d)
                    seen.add(d.service_name)
            definitions = unique_definitions
        else:
            # List all available integrations
            definitions = ctx.deps.integration_registry.list_integrations()
        
        results = []
        for definition in definitions:
            # Check if user has configured this service
            client = await ctx.deps.integration_manager.get_client(
                definition.service_name, ctx.deps.user_id
            )
            
            status = IntegrationStatus.CONFIGURED if client else IntegrationStatus.AVAILABLE
            if not definition.config.enabled:
                status = IntegrationStatus.DISABLED
            elif definition.status == "error":
                status = IntegrationStatus.ERROR
            
            results.append(ServiceDiscoveryResult(
                service_name=definition.service_name,
                display_name=definition.config.display_name,
                description=definition.config.description,
                auth_type=definition.config.auth_type,
                capabilities=definition.config.capabilities,
                status=status,
                configuration_required=not bool(client),
                health_status=definition.status
            ))
        
        return results
    
    except Exception as e:
        logger.error(f"Service discovery failed: {e}")
        return []


@integration_agent.tool
async def configure_integration(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str,
    credentials: Dict[str, Any],
    custom_config: Optional[Dict[str, Any]] = None
) -> IntegrationTestResult:
    """Configure an integration with user credentials."""
    try:
        # Configure the integration
        success = await ctx.deps.integration_manager.configure_integration(
            service_name=service_name,
            credentials=credentials,
            user_id=ctx.deps.user_id,
            custom_config=custom_config
        )
        
        if success:
            # Test the integration
            test_result = await test_integration_connection(ctx, service_name)
            return test_result
        else:
            return IntegrationTestResult(
                service_name=service_name,
                success=False,
                message="Failed to configure integration",
                error_details={"error": "Configuration failed"}
            )
    
    except Exception as e:
        logger.error(f"Integration configuration failed: {e}")
        return IntegrationTestResult(
            service_name=service_name,
            success=False,
            message=f"Configuration error: {str(e)}",
            error_details={"error": str(e), "type": type(e).__name__}
        )


@integration_agent.tool
async def test_integration_connection(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str
) -> IntegrationTestResult:
    """Test connection to an integrated service."""
    start_time = time.time()
    
    try:
        # Get the client
        client = await ctx.deps.integration_manager.get_client(
            service_name, ctx.deps.user_id
        )
        
        if not client:
            return IntegrationTestResult(
                service_name=service_name,
                success=False,
                message="Integration not configured",
                response_time=time.time() - start_time
            )
        
        # Get service definition to check capabilities
        definition = ctx.deps.integration_registry.get_integration(service_name)
        if not definition:
            return IntegrationTestResult(
                service_name=service_name,
                success=False,
                message="Service not found in registry",
                response_time=time.time() - start_time
            )
        
        # Test basic connectivity
        try:
            response = await client.get("/")
            success = response.status_code < 500
            message = "Connection successful" if success else f"Connection failed: HTTP {response.status_code}"
        except Exception as e:
            success = False
            message = f"Connection test failed: {str(e)}"
        
        response_time = time.time() - start_time
        
        return IntegrationTestResult(
            service_name=service_name,
            success=success,
            message=message,
            response_time=response_time,
            capabilities_verified=definition.config.capabilities if success else [],
            error_details={"error": message} if not success else None
        )
    
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        return IntegrationTestResult(
            service_name=service_name,
            success=False,
            message=f"Test error: {str(e)}",
            response_time=time.time() - start_time,
            error_details={"error": str(e), "type": type(e).__name__}
        )


@integration_agent.tool
async def start_authentication_flow(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str
) -> AuthenticationFlow:
    """Start authentication flow for a service."""
    try:
        definition = ctx.deps.integration_registry.get_integration(service_name)
        if not definition:
            raise IntegrationError(f"Service {service_name} not found")
        
        flow_id = str(uuid.uuid4())
        auth_type = definition.config.auth_type
        
        if auth_type == AuthType.OAUTH2:
            # Create OAuth handler and generate authorization URL
            oauth_config = definition.config.auth_config
            oauth_handler = OAuthHandler(oauth_config)
            
            auth_url, state = oauth_handler.generate_authorization_url(ctx.deps.user_id)
            
            return AuthenticationFlow(
                service_name=service_name,
                auth_type=auth_type,
                flow_id=flow_id,
                authorization_url=auth_url,
                instructions=f"Please visit the authorization URL to grant access to {definition.config.display_name}",
                expires_at=datetime.now() + timedelta(minutes=10)
            )
        
        elif auth_type == AuthType.API_KEY:
            return AuthenticationFlow(
                service_name=service_name,
                auth_type=auth_type,
                flow_id=flow_id,
                required_fields=["api_key"],
                instructions=f"Please provide your API key for {definition.config.display_name}"
            )
        
        elif auth_type == AuthType.BASIC_AUTH:
            return AuthenticationFlow(
                service_name=service_name,
                auth_type=auth_type,
                flow_id=flow_id,
                required_fields=["username", "password"],
                instructions=f"Please provide your username and password for {definition.config.display_name}"
            )
        
        else:
            return AuthenticationFlow(
                service_name=service_name,
                auth_type=auth_type,
                flow_id=flow_id,
                instructions=f"Custom authentication required for {definition.config.display_name}"
            )
    
    except Exception as e:
        logger.error(f"Failed to start authentication flow: {e}")
        raise


@integration_agent.tool
async def execute_service_operation(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str,
    operation: str,
    parameters: Dict[str, Any] = None
) -> IntegrationOperationResult:
    """Execute an operation on an integrated service."""
    start_time = time.time()
    parameters = parameters or {}
    
    try:
        result = await ctx.deps.integration_manager.execute_operation(
            service_name=service_name,
            user_id=ctx.deps.user_id,
            operation=operation,
            **parameters
        )
        
        execution_time = time.time() - start_time
        
        return IntegrationOperationResult(
            service_name=service_name,
            operation=operation,
            success=True,
            result=result.json() if hasattr(result, 'json') else result,
            execution_time=execution_time
        )
    
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Service operation failed: {e}")
        
        return IntegrationOperationResult(
            service_name=service_name,
            operation=operation,
            success=False,
            error_message=str(e),
            execution_time=execution_time
        )


@integration_agent.tool
async def check_service_capabilities(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str,
    required_capabilities: List[str]
) -> IntegrationCapabilityResult:
    """Check if a service supports required capabilities."""
    try:
        definition = ctx.deps.integration_registry.get_integration(service_name)
        if not definition:
            return IntegrationCapabilityResult(
                service_name=service_name,
                supported_capabilities=[],
                missing_capabilities=[ServiceCapability(cap) for cap in required_capabilities],
                is_compatible=False
            )
        
        supported_caps = definition.config.capabilities
        required_caps = [ServiceCapability(cap) for cap in required_capabilities]
        
        missing_caps = [cap for cap in required_caps if cap not in supported_caps]
        is_compatible = len(missing_caps) == 0
        
        # Find alternative services if not compatible
        alternatives = []
        if not is_compatible:
            for cap in missing_caps:
                alt_definitions = ctx.deps.integration_registry.get_integrations_by_capability(cap)
                alternatives.extend([d.service_name for d in alt_definitions if d.service_name != service_name])
        
        return IntegrationCapabilityResult(
            service_name=service_name,
            supported_capabilities=supported_caps,
            missing_capabilities=missing_caps,
            is_compatible=is_compatible,
            alternative_services=list(set(alternatives))
        )
    
    except Exception as e:
        logger.error(f"Capability check failed: {e}")
        return IntegrationCapabilityResult(
            service_name=service_name,
            supported_capabilities=[],
            missing_capabilities=[ServiceCapability(cap) for cap in required_capabilities],
            is_compatible=False
        )


@integration_agent.tool
async def get_integration_health(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str
) -> IntegrationHealth:
    """Get health status of an integration."""
    try:
        status = await ctx.deps.integration_manager.get_integration_status(service_name)
        
        return IntegrationHealth(
            service_name=service_name,
            status=status.get("status", "unknown"),
            last_check=datetime.now(),
            error_count=status.get("error_count", 0),
            last_error=status.get("last_error"),
            uptime_percentage=95.0 if status.get("is_healthy") else 50.0
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return IntegrationHealth(
            service_name=service_name,
            status="error",
            last_check=datetime.now(),
            error_count=1,
            last_error=str(e),
            uptime_percentage=0.0
        )


@integration_agent.tool
async def list_user_integrations(
    ctx: RunContext[IntegrationAgentDeps]
) -> List[Dict[str, Any]]:
    """List all integrations configured for the current user."""
    try:
        integrations = await ctx.deps.integration_manager.list_user_integrations(
            ctx.deps.user_id
        )
        return integrations
    
    except Exception as e:
        logger.error(f"Failed to list user integrations: {e}")
        return []


@integration_agent.tool
async def remove_integration(
    ctx: RunContext[IntegrationAgentDeps],
    service_name: str
) -> bool:
    """Remove an integration for the current user."""
    try:
        success = await ctx.deps.integration_manager.remove_integration(
            service_name, ctx.deps.user_id
        )
        return success
    
    except Exception as e:
        logger.error(f"Failed to remove integration: {e}")
        return False


# Helper functions for using the integration agent
async def discover_integrations(
    user_id: str,
    query: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
    integration_manager: IntegrationManager = None,
    integration_registry: IntegrationRegistry = None
) -> IntegrationAgentResult:
    """Discover available integrations."""
    deps = IntegrationAgentDeps(
        integration_manager=integration_manager or integration_manager,
        integration_registry=integration_registry or integration_registry,
        user_id=user_id
    )
    
    prompt = f"Discover services"
    if query:
        prompt += f" matching '{query}'"
    if capabilities:
        prompt += f" with capabilities: {', '.join(capabilities)}"
    
    result = await integration_agent.run(prompt, deps=deps)
    return result.output


async def setup_integration(
    user_id: str,
    service_name: str,
    credentials: Dict[str, Any],
    custom_config: Optional[Dict[str, Any]] = None,
    integration_manager: IntegrationManager = None,
    integration_registry: IntegrationRegistry = None
) -> IntegrationAgentResult:
    """Set up an integration with credentials."""
    deps = IntegrationAgentDeps(
        integration_manager=integration_manager or integration_manager,
        integration_registry=integration_registry or integration_registry,
        user_id=user_id
    )
    
    prompt = f"Configure integration for {service_name} with the provided credentials"
    
    result = await integration_agent.run(prompt, deps=deps)
    return result.output