"""API endpoints for integration management."""

from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from src.agents.integration_agent import (
    integration_agent,
    IntegrationAgentDeps,
    discover_integrations,
    setup_integration
)
from src.models.integration import (
    IntegrationConfig,
    IntegrationTestResult,
    ServiceDiscoveryResult,
    IntegrationOperation,
    IntegrationOperationResult,
    AuthenticationFlow,
    IntegrationHealth
)
from src.integrations.manager import integration_manager
from src.integrations.registry import integration_registry
from src.services.database import DatabaseService, get_db
from src.dependencies import get_current_user
from src.models.user import User

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationSetupRequest(BaseModel):
    """Request to set up an integration."""
    service_name: str = Field(..., description="Name of the service")
    credentials: Dict[str, Any] = Field(..., description="Authentication credentials")
    custom_config: Optional[Dict[str, Any]] = Field(None, description="Custom configuration")


class IntegrationOperationRequest(BaseModel):
    """Request to perform an operation on an integration."""
    operation: str = Field(..., description="Operation to perform")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Operation parameters")


class IntegrationDiscoveryRequest(BaseModel):
    """Request to discover integrations."""
    query: Optional[str] = Field(None, description="Search query")
    capabilities: Optional[List[str]] = Field(None, description="Required capabilities")


@router.get("/discover", response_model=List[ServiceDiscoveryResult])
async def discover_services(
    query: Optional[str] = None,
    capabilities: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Discover available services and integrations."""
    try:
        # Parse capabilities if provided
        capability_list = None
        if capabilities:
            capability_list = [cap.strip() for cap in capabilities.split(",")]
        
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Use the integration agent to discover services
        services = await integration_agent.run_tool(
            "discover_services",
            deps=deps,
            query=query,
            capabilities=capability_list
        )
        
        return services
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service discovery failed: {str(e)}")


@router.post("/setup", response_model=IntegrationTestResult)
async def setup_integration_endpoint(
    request: IntegrationSetupRequest,
    current_user: User = Depends(get_current_user)
):
    """Set up an integration with user credentials."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Configure the integration
        result = await integration_agent.run_tool(
            "configure_integration",
            deps=deps,
            service_name=request.service_name,
            credentials=request.credentials,
            custom_config=request.custom_config
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Integration setup failed: {str(e)}")


@router.get("/test/{service_name}", response_model=IntegrationTestResult)
async def test_integration(
    service_name: str,
    current_user: User = Depends(get_current_user)
):
    """Test connection to an integrated service."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Test the integration
        result = await integration_agent.run_tool(
            "test_integration_connection",
            deps=deps,
            service_name=service_name
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Integration test failed: {str(e)}")


@router.post("/auth/{service_name}", response_model=AuthenticationFlow)
async def start_auth_flow(
    service_name: str,
    current_user: User = Depends(get_current_user)
):
    """Start authentication flow for a service."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Start authentication flow
        result = await integration_agent.run_tool(
            "start_authentication_flow",
            deps=deps,
            service_name=service_name
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication flow failed: {str(e)}")


@router.post("/{service_name}/execute", response_model=IntegrationOperationResult)
async def execute_operation(
    service_name: str,
    request: IntegrationOperationRequest,
    current_user: User = Depends(get_current_user)
):
    """Execute an operation on an integrated service."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Execute the operation
        result = await integration_agent.run_tool(
            "execute_service_operation",
            deps=deps,
            service_name=service_name,
            operation=request.operation,
            parameters=request.parameters
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Operation execution failed: {str(e)}")


@router.get("/{service_name}/health", response_model=IntegrationHealth)
async def get_integration_health(
    service_name: str,
    current_user: User = Depends(get_current_user)
):
    """Get health status of an integration."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Get health status
        result = await integration_agent.run_tool(
            "get_integration_health",
            deps=deps,
            service_name=service_name
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/", response_model=List[Dict[str, Any]])
async def list_user_integrations(
    current_user: User = Depends(get_current_user)
):
    """List all integrations configured for the current user."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # List user integrations
        result = await integration_agent.run_tool(
            "list_user_integrations",
            deps=deps
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list integrations: {str(e)}")


@router.delete("/{service_name}")
async def remove_integration(
    service_name: str,
    current_user: User = Depends(get_current_user)
):
    """Remove an integration for the current user."""
    try:
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Remove the integration
        success = await integration_agent.run_tool(
            "remove_integration",
            deps=deps,
            service_name=service_name
        )
        
        if success:
            return {"message": f"Integration {service_name} removed successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to remove integration")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove integration: {str(e)}")


@router.get("/{service_name}/capabilities")
async def check_service_capabilities(
    service_name: str,
    required_capabilities: str,
    current_user: User = Depends(get_current_user)
):
    """Check if a service supports required capabilities."""
    try:
        # Parse required capabilities
        capability_list = [cap.strip() for cap in required_capabilities.split(",")]
        
        # Create agent dependencies
        deps = IntegrationAgentDeps(
            integration_manager=integration_manager,
            integration_registry=integration_registry,
            user_id=str(current_user.id)
        )
        
        # Check capabilities
        result = await integration_agent.run_tool(
            "check_service_capabilities",
            deps=deps,
            service_name=service_name,
            required_capabilities=capability_list
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Capability check failed: {str(e)}")


# Webhook endpoints for OAuth callbacks
@router.get("/oauth/callback/{service_name}")
async def oauth_callback(
    service_name: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None
):
    """Handle OAuth callback from external services."""
    try:
        if error:
            raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
        
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing code or state parameter")
        
        # TODO: Handle OAuth callback with the authentication manager
        # This would involve:
        # 1. Validating the state parameter
        # 2. Exchanging the code for tokens
        # 3. Storing the tokens securely
        # 4. Redirecting the user back to the application
        
        return {"message": "OAuth callback received", "service": service_name}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {str(e)}")


@router.post("/webhook/{service_name}")
async def webhook_handler(
    service_name: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks
):
    """Handle webhooks from external services."""
    try:
        # TODO: Implement webhook handling
        # This would involve:
        # 1. Verifying the webhook signature
        # 2. Processing the webhook payload
        # 3. Triggering appropriate workflows or notifications
        
        background_tasks.add_task(process_webhook, service_name, payload)
        
        return {"message": "Webhook received", "service": service_name}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")


async def process_webhook(service_name: str, payload: Dict[str, Any]):
    """Process webhook payload in the background."""
    try:
        # TODO: Implement webhook processing logic
        print(f"Processing webhook from {service_name}: {payload}")
    except Exception as e:
        print(f"Webhook processing error: {e}")