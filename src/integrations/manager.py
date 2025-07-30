"""Integration manager for handling service integrations."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import httpx

from .registry import IntegrationRegistry, IntegrationDefinition, integration_registry
from .config import IntegrationConfig, ServiceCapability
from .auth import AuthenticationManager
from .clients import BaseAPIClient, HTTPClient
from ..errors import IntegrationError, IntegrationErrorHandler, global_error_handler
from ..services.database import DatabaseService

logger = logging.getLogger(__name__)


class IntegrationManager:
    """Manager for handling service integrations."""
    
    def __init__(
        self,
        registry: IntegrationRegistry = None,
        db: Optional[DatabaseService] = None
    ):
        self.registry = registry or integration_registry
        self.db = db
        self.auth_manager = AuthenticationManager()
        self.clients: Dict[str, BaseAPIClient] = {}
        self.error_handler = IntegrationErrorHandler(global_error_handler)
        self.health_check_tasks: Dict[str, asyncio.Task] = {}
        self.rate_limiters: Dict[str, Any] = {}
    
    async def initialize(self):
        """Initialize the integration manager."""
        logger.info("Initializing Integration Manager")
        
        # Start health checks for configured integrations
        for definition in self.registry.list_integrations(status_filter="configured"):
            await self._start_health_check(definition.service_name)
    
    async def configure_integration(
        self,
        service_name: str,
        credentials: Dict[str, Any],
        user_id: str,
        custom_config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Configure an integration with user credentials."""
        definition = self.registry.get_integration(service_name)
        if not definition:
            raise IntegrationError(
                f"Integration '{service_name}' not found in registry",
                service=service_name
            )
        
        try:
            # Store credentials securely
            await self.auth_manager.store_credentials(
                service_name=service_name,
                user_id=user_id,
                credentials=credentials,
                auth_type=definition.config.auth_type
            )
            
            # Update custom configuration if provided
            if custom_config:
                definition.config.custom_config.update(custom_config)
            
            # Create API client
            client = await self._create_client(service_name, user_id)
            if client:
                self.clients[f"{service_name}:{user_id}"] = client
            
            # Test the connection
            if await self._test_connection(service_name, user_id):
                definition.status = "configured"
                definition.mark_healthy()
                
                # Start health checks
                await self._start_health_check(service_name)
                
                logger.info(f"Successfully configured integration: {service_name}")
                return True
            else:
                raise IntegrationError(
                    f"Failed to test connection for {service_name}",
                    service=service_name
                )
        
        except Exception as e:
            definition.mark_error(str(e))
            await self.error_handler.handle_integration_error(
                e, service_name, "configure"
            )
            raise
    
    async def get_client(self, service_name: str, user_id: str) -> Optional[BaseAPIClient]:
        """Get an API client for a service and user."""
        client_key = f"{service_name}:{user_id}"
        
        if client_key in self.clients:
            return self.clients[client_key]
        
        # Try to create client if not exists
        client = await self._create_client(service_name, user_id)
        if client:
            self.clients[client_key] = client
        
        return client
    
    async def _create_client(self, service_name: str, user_id: str) -> Optional[BaseAPIClient]:
        """Create an API client for a service."""
        definition = self.registry.get_integration(service_name)
        if not definition:
            return None
        
        try:
            # Get authentication
            auth = await self.auth_manager.get_authentication(service_name, user_id)
            if not auth:
                logger.warning(f"No authentication found for {service_name}:{user_id}")
                return None
            
            # Create HTTP client
            client = HTTPClient(
                base_url=definition.config.base_url,
                auth=auth,
                headers=definition.config.default_headers,
                timeout=definition.config.timeout,
                rate_limit=definition.config.rate_limit
            )
            
            return client
        
        except Exception as e:
            logger.error(f"Failed to create client for {service_name}: {e}")
            return None
    
    async def _test_connection(self, service_name: str, user_id: str) -> bool:
        """Test connection to a service."""
        client = await self.get_client(service_name, user_id)
        if not client:
            return False
        
        definition = self.registry.get_integration(service_name)
        health_check_url = definition.config.health_check_url
        
        try:
            if health_check_url:
                response = await client.get(health_check_url)
                return response.status_code < 400
            else:
                # Try a simple GET request to the base URL
                response = await client.get("/")
                return response.status_code < 500  # Allow 4xx for auth issues
        
        except Exception as e:
            logger.warning(f"Connection test failed for {service_name}: {e}")
            return False
    
    async def _start_health_check(self, service_name: str):
        """Start periodic health checks for a service."""
        if service_name in self.health_check_tasks:
            return  # Already running
        
        async def health_check_loop():
            while True:
                try:
                    await asyncio.sleep(300)  # Check every 5 minutes
                    
                    definition = self.registry.get_integration(service_name)
                    if not definition or definition.status != "configured":
                        break
                    
                    # Get all users for this service
                    users = await self._get_service_users(service_name)
                    
                    healthy = False
                    for user_id in users:
                        if await self._test_connection(service_name, user_id):
                            healthy = True
                            break
                    
                    if healthy:
                        definition.mark_healthy()
                    else:
                        definition.mark_error("Health check failed")
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health check error for {service_name}: {e}")
        
        task = asyncio.create_task(health_check_loop())
        self.health_check_tasks[service_name] = task
    
    async def _get_service_users(self, service_name: str) -> List[str]:
        """Get all users who have configured a service."""
        if not self.db:
            return []
        
        try:
            query = """
                SELECT DISTINCT user_id 
                FROM user_integrations 
                WHERE service_name = $1 AND status = 'active'
            """
            rows = await self.db.fetch(query, service_name)
            return [row['user_id'] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get users for service {service_name}: {e}")
            return []
    
    async def execute_operation(
        self,
        service_name: str,
        user_id: str,
        operation: str,
        **kwargs
    ) -> Any:
        """Execute an operation on a service."""
        client = await self.get_client(service_name, user_id)
        if not client:
            raise IntegrationError(
                f"No client available for {service_name}",
                service=service_name,
                operation=operation
            )
        
        try:
            # Execute the operation based on type
            if operation == "get":
                return await client.get(kwargs.get("path", "/"), params=kwargs.get("params"))
            elif operation == "post":
                return await client.post(
                    kwargs.get("path", "/"),
                    json=kwargs.get("data"),
                    params=kwargs.get("params")
                )
            elif operation == "put":
                return await client.put(
                    kwargs.get("path", "/"),
                    json=kwargs.get("data"),
                    params=kwargs.get("params")
                )
            elif operation == "delete":
                return await client.delete(kwargs.get("path", "/"), params=kwargs.get("params"))
            else:
                raise IntegrationError(
                    f"Unsupported operation: {operation}",
                    service=service_name,
                    operation=operation
                )
        
        except Exception as e:
            await self.error_handler.handle_integration_error(
                e, service_name, operation
            )
            raise
    
    async def get_service_capabilities(self, service_name: str) -> List[ServiceCapability]:
        """Get capabilities for a service."""
        definition = self.registry.get_integration(service_name)
        if not definition:
            return []
        
        return definition.config.capabilities
    
    async def find_services_by_capability(
        self,
        capability: ServiceCapability,
        user_id: Optional[str] = None
    ) -> List[str]:
        """Find services that support a specific capability."""
        definitions = self.registry.get_integrations_by_capability(capability)
        
        if not user_id:
            return [d.service_name for d in definitions]
        
        # Filter by user's configured services
        configured_services = []
        for definition in definitions:
            client = await self.get_client(definition.service_name, user_id)
            if client:
                configured_services.append(definition.service_name)
        
        return configured_services
    
    async def get_integration_status(self, service_name: str) -> Dict[str, Any]:
        """Get detailed status for an integration."""
        definition = self.registry.get_integration(service_name)
        if not definition:
            return {"error": "Integration not found"}
        
        return {
            "service_name": service_name,
            "display_name": definition.config.display_name,
            "status": definition.status,
            "is_healthy": definition.is_healthy,
            "last_health_check": definition.last_health_check.isoformat() if definition.last_health_check else None,
            "error_count": definition.error_count,
            "last_error": definition.last_error,
            "capabilities": [cap.value for cap in definition.config.capabilities],
            "enabled": definition.config.enabled
        }
    
    async def list_user_integrations(self, user_id: str) -> List[Dict[str, Any]]:
        """List all integrations configured for a user."""
        integrations = []
        
        for definition in self.registry.list_integrations():
            client = await self.get_client(definition.service_name, user_id)
            
            integrations.append({
                "service_name": definition.service_name,
                "display_name": definition.config.display_name,
                "description": definition.config.description,
                "configured": client is not None,
                "status": definition.status,
                "capabilities": [cap.value for cap in definition.config.capabilities]
            })
        
        return integrations
    
    async def remove_integration(self, service_name: str, user_id: str) -> bool:
        """Remove an integration for a user."""
        try:
            # Remove credentials
            await self.auth_manager.remove_credentials(service_name, user_id)
            
            # Remove client
            client_key = f"{service_name}:{user_id}"
            if client_key in self.clients:
                del self.clients[client_key]
            
            # Update database
            if self.db:
                query = """
                    UPDATE user_integrations 
                    SET status = 'removed' 
                    WHERE service_name = $1 AND user_id = $2
                """
                await self.db.execute(query, service_name, user_id)
            
            logger.info(f"Removed integration {service_name} for user {user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to remove integration {service_name}: {e}")
            return False
    
    async def shutdown(self):
        """Shutdown the integration manager."""
        logger.info("Shutting down Integration Manager")
        
        # Cancel health check tasks
        for task in self.health_check_tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self.health_check_tasks:
            await asyncio.gather(
                *self.health_check_tasks.values(),
                return_exceptions=True
            )
        
        # Close all clients
        for client in self.clients.values():
            if hasattr(client, 'close'):
                await client.close()
        
        self.clients.clear()
        self.health_check_tasks.clear()


# Global integration manager instance
integration_manager = IntegrationManager()