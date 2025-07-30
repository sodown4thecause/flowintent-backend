"""Integration registry for managing available integrations."""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .config import IntegrationConfig, ServiceCapability, PREDEFINED_INTEGRATIONS
from ..errors import IntegrationError

logger = logging.getLogger(__name__)


@dataclass
class IntegrationDefinition:
    """Definition of an available integration."""
    
    config: IntegrationConfig
    status: str = "available"  # available, configured, error, disabled
    last_health_check: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_healthy(self) -> bool:
        """Check if the integration is healthy."""
        return self.status in ["available", "configured"] and self.error_count < 5
    
    @property
    def service_name(self) -> str:
        """Get the service name."""
        return self.config.service_name
    
    def mark_error(self, error_message: str):
        """Mark the integration as having an error."""
        self.status = "error"
        self.error_count += 1
        self.last_error = error_message
        logger.warning(f"Integration {self.service_name} error: {error_message}")
    
    def mark_healthy(self):
        """Mark the integration as healthy."""
        if self.status == "error":
            self.status = "available"
        self.error_count = 0
        self.last_error = None
        self.last_health_check = datetime.now()


class IntegrationRegistry:
    """Registry for managing available integrations."""
    
    def __init__(self):
        self.integrations: Dict[str, IntegrationDefinition] = {}
        self.capabilities_index: Dict[ServiceCapability, Set[str]] = {}
        self._load_predefined_integrations()
    
    def _load_predefined_integrations(self):
        """Load predefined integrations into the registry."""
        for service_name, config in PREDEFINED_INTEGRATIONS.items():
            self.register_integration(config)
    
    def register_integration(self, config: IntegrationConfig) -> IntegrationDefinition:
        """Register a new integration."""
        definition = IntegrationDefinition(config=config)
        self.integrations[config.service_name] = definition
        
        # Update capabilities index
        for capability in config.capabilities:
            if capability not in self.capabilities_index:
                self.capabilities_index[capability] = set()
            self.capabilities_index[capability].add(config.service_name)
        
        logger.info(f"Registered integration: {config.service_name}")
        return definition
    
    def unregister_integration(self, service_name: str) -> bool:
        """Unregister an integration."""
        if service_name not in self.integrations:
            return False
        
        definition = self.integrations[service_name]
        
        # Remove from capabilities index
        for capability in definition.config.capabilities:
            if capability in self.capabilities_index:
                self.capabilities_index[capability].discard(service_name)
                if not self.capabilities_index[capability]:
                    del self.capabilities_index[capability]
        
        del self.integrations[service_name]
        logger.info(f"Unregistered integration: {service_name}")
        return True
    
    def get_integration(self, service_name: str) -> Optional[IntegrationDefinition]:
        """Get an integration by service name."""
        return self.integrations.get(service_name)
    
    def list_integrations(
        self,
        status_filter: Optional[str] = None,
        capability_filter: Optional[ServiceCapability] = None,
        enabled_only: bool = True
    ) -> List[IntegrationDefinition]:
        """List integrations with optional filters."""
        integrations = list(self.integrations.values())
        
        # Filter by status
        if status_filter:
            integrations = [i for i in integrations if i.status == status_filter]
        
        # Filter by capability
        if capability_filter:
            integrations = [
                i for i in integrations 
                if capability_filter in i.config.capabilities
            ]
        
        # Filter by enabled status
        if enabled_only:
            integrations = [i for i in integrations if i.config.enabled]
        
        return integrations
    
    def get_integrations_by_capability(
        self,
        capability: ServiceCapability
    ) -> List[IntegrationDefinition]:
        """Get all integrations that support a specific capability."""
        service_names = self.capabilities_index.get(capability, set())
        return [
            self.integrations[name] 
            for name in service_names 
            if name in self.integrations and self.integrations[name].config.enabled
        ]
    
    def search_integrations(
        self,
        query: str,
        capabilities: Optional[List[ServiceCapability]] = None
    ) -> List[IntegrationDefinition]:
        """Search integrations by name or description."""
        query = query.lower()
        results = []
        
        for definition in self.integrations.values():
            if not definition.config.enabled:
                continue
            
            # Check if query matches name or description
            if (query in definition.config.service_name.lower() or 
                query in definition.config.display_name.lower() or
                query in definition.config.description.lower()):
                
                # Filter by capabilities if specified
                if capabilities:
                    if any(cap in definition.config.capabilities for cap in capabilities):
                        results.append(definition)
                else:
                    results.append(definition)
        
        return results
    
    def update_integration_status(
        self,
        service_name: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """Update the status of an integration."""
        definition = self.get_integration(service_name)
        if not definition:
            return False
        
        definition.status = status
        if error_message:
            definition.mark_error(error_message)
        elif status in ["available", "configured"]:
            definition.mark_healthy()
        
        return True
    
    def get_integration_stats(self) -> Dict[str, Any]:
        """Get statistics about registered integrations."""
        total = len(self.integrations)
        by_status = {}
        by_capability = {}
        
        for definition in self.integrations.values():
            # Count by status
            status = definition.status
            by_status[status] = by_status.get(status, 0) + 1
            
            # Count by capability
            for capability in definition.config.capabilities:
                cap_name = capability.value
                by_capability[cap_name] = by_capability.get(cap_name, 0) + 1
        
        return {
            "total_integrations": total,
            "by_status": by_status,
            "by_capability": by_capability,
            "healthy_integrations": len([
                d for d in self.integrations.values() if d.is_healthy
            ])
        }
    
    def validate_integration_config(self, config: IntegrationConfig) -> List[str]:
        """Validate an integration configuration."""
        errors = []
        
        # Check for duplicate service names
        if config.service_name in self.integrations:
            errors.append(f"Integration with name '{config.service_name}' already exists")
        
        # Validate auth configuration
        if config.auth_type.value not in ["api_key", "oauth2", "basic_auth", "bearer_token", "custom"]:
            errors.append(f"Invalid auth type: {config.auth_type}")
        
        # Validate capabilities
        for capability in config.capabilities:
            if not isinstance(capability, ServiceCapability):
                errors.append(f"Invalid capability: {capability}")
        
        # Validate URLs
        if not config.base_url.startswith(('http://', 'https://')):
            errors.append("Base URL must start with http:// or https://")
        
        return errors
    
    def export_registry(self) -> Dict[str, Any]:
        """Export the registry configuration."""
        return {
            "integrations": {
                name: {
                    "config": definition.config.dict(),
                    "status": definition.status,
                    "last_health_check": definition.last_health_check.isoformat() if definition.last_health_check else None,
                    "error_count": definition.error_count,
                    "last_error": definition.last_error,
                    "metadata": definition.metadata
                }
                for name, definition in self.integrations.items()
            },
            "capabilities_index": {
                capability.value: list(services)
                for capability, services in self.capabilities_index.items()
            }
        }
    
    def import_registry(self, data: Dict[str, Any]):
        """Import registry configuration."""
        integrations_data = data.get("integrations", {})
        
        for service_name, integration_data in integrations_data.items():
            try:
                config = IntegrationConfig(**integration_data["config"])
                definition = IntegrationDefinition(
                    config=config,
                    status=integration_data.get("status", "available"),
                    error_count=integration_data.get("error_count", 0),
                    last_error=integration_data.get("last_error"),
                    metadata=integration_data.get("metadata", {})
                )
                
                if integration_data.get("last_health_check"):
                    definition.last_health_check = datetime.fromisoformat(
                        integration_data["last_health_check"]
                    )
                
                self.integrations[service_name] = definition
                
                # Update capabilities index
                for capability in config.capabilities:
                    if capability not in self.capabilities_index:
                        self.capabilities_index[capability] = set()
                    self.capabilities_index[capability].add(service_name)
                
            except Exception as e:
                logger.error(f"Failed to import integration {service_name}: {e}")


# Global registry instance
integration_registry = IntegrationRegistry()