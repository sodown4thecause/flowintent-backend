"""Integration service for managing external service connections."""

import asyncio
import httpx
import json
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from src.config import settings
from src.models.integration import (
    IntegrationConfig,
    IntegrationCredentials,
    IntegrationTest,
    IntegrationTestResult,
    ServiceCapability,
    IntegrationRegistry
)
from src.services.database import DatabaseService


class IntegrationService:
    """Service for managing external integrations."""
    
    def __init__(self, db: DatabaseService):
        self.db = db
        self._registry = None
        self._encryption_key = None
    
    def _get_encryption_key(self) -> bytes:
        """Get or create encryption key for credentials."""
        if self._encryption_key is None:
            # Derive key from secret key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'integration_salt',  # In production, use a random salt
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(settings.secret_key.encode()))
            self._encryption_key = key
        return self._encryption_key
    
    def _encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """Encrypt credentials for storage."""
        f = Fernet(self._get_encryption_key())
        return f.encrypt(json.dumps(credentials).encode()).decode()
    
    def _decrypt_credentials(self, encrypted_credentials: str) -> Dict[str, Any]:
        """Decrypt credentials from storage."""
        f = Fernet(self._get_encryption_key())
        return json.loads(f.decrypt(encrypted_credentials.encode()).decode())
    
    async def get_integration_registry(self) -> IntegrationRegistry:
        """Get the integration registry with all available services."""
        if self._registry is None:
            await self._initialize_registry()
        return self._registry
    
    async def _initialize_registry(self):
        """Initialize the integration registry with supported services."""
        self._registry = IntegrationRegistry()
        
        # Google Services
        google_drive_config = IntegrationConfig(
            service_name="google_drive",
            auth_type="oauth2",
            capabilities=["read_files", "write_files", "list_files", "create_folder"],
            required_scopes=["https://www.googleapis.com/auth/drive"],
            base_url="https://www.googleapis.com/drive/v3",
            rate_limits={"requests_per_second": 10}
        )
        self._registry.add_service(google_drive_config)
        
        google_sheets_config = IntegrationConfig(
            service_name="google_sheets",
            auth_type="oauth2",
            capabilities=["read_sheet", "write_sheet", "create_sheet", "format_cells"],
            required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
            base_url="https://sheets.googleapis.com/v4",
            rate_limits={"requests_per_second": 5}
        )
        self._registry.add_service(google_sheets_config)
        
        google_calendar_config = IntegrationConfig(
            service_name="google_calendar",
            auth_type="oauth2",
            capabilities=["read_events", "create_event", "update_event", "delete_event"],
            required_scopes=["https://www.googleapis.com/auth/calendar"],
            base_url="https://www.googleapis.com/calendar/v3",
            rate_limits={"requests_per_second": 5}
        )
        self._registry.add_service(google_calendar_config)
        
        # Slack
        slack_config = IntegrationConfig(
            service_name="slack",
            auth_type="oauth2",
            capabilities=["send_message", "read_channel", "upload_file", "create_channel"],
            required_scopes=["chat:write", "channels:read", "files:write"],
            base_url="https://slack.com/api",
            rate_limits={"requests_per_second": 1}
        )
        self._registry.add_service(slack_config)
        
        # Twitter/X
        twitter_config = IntegrationConfig(
            service_name="twitter",
            auth_type="oauth2",
            capabilities=["post_tweet", "read_timeline", "send_dm", "upload_media"],
            required_scopes=["tweet.read", "tweet.write", "users.read"],
            base_url="https://api.twitter.com/2",
            rate_limits={"requests_per_second": 1}
        )
        self._registry.add_service(twitter_config)
        
        # OpenAI
        openai_config = IntegrationConfig(
            service_name="openai",
            auth_type="api_key",
            capabilities=["generate_text", "generate_image", "create_embedding", "moderate_content"],
            required_scopes=[],
            base_url="https://api.openai.com/v1",
            rate_limits={"requests_per_minute": 60}
        )
        self._registry.add_service(openai_config)
        
        # Email (SMTP)
        email_config = IntegrationConfig(
            service_name="email",
            auth_type="api_key",
            capabilities=["send_email", "read_email", "search_email"],
            required_scopes=[],
            base_url="smtp://",
            rate_limits={"requests_per_minute": 30}
        )
        self._registry.add_service(email_config)
    
    async def get_user_integrations(self, user_id: str) -> List[IntegrationCredentials]:
        """Get all integrations configured by a user."""
        query = """
            SELECT id, user_id, service_name, auth_data, configuration, status, 
                   created_at, last_used
            FROM user_integrations 
            WHERE user_id = $1 AND status = 'active'
        """
        
        rows = await self.db.fetch(query, user_id)
        integrations = []
        
        for row in rows:
            # Decrypt credentials
            try:
                credentials = self._decrypt_credentials(row['auth_data'])
                
                integration = IntegrationCredentials(
                    id=row['id'],
                    user_id=row['user_id'],
                    service_name=row['service_name'],
                    auth_type=credentials.get('auth_type', 'api_key'),
                    credentials=credentials,
                    status=row['status'],
                    created_at=row['created_at'],
                    last_used=row['last_used']
                )
                integrations.append(integration)
            except Exception as e:
                print(f"Error decrypting credentials for {row['service_name']}: {e}")
                continue
        
        return integrations
    
    async def store_credentials(self, credentials: IntegrationCredentials) -> bool:
        """Store encrypted credentials for a user."""
        try:
            # Encrypt credentials
            encrypted_creds = self._encrypt_credentials(credentials.credentials)
            
            # Store in database
            query = """
                INSERT INTO user_integrations (
                    user_id, service_name, auth_data, configuration, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, service_name) 
                DO UPDATE SET 
                    auth_data = $3,
                    configuration = $4,
                    status = $5,
                    created_at = $6
            """
            
            await self.db.execute(
                query,
                credentials.user_id,
                credentials.service_name,
                encrypted_creds,
                {},  # configuration
                credentials.status,
                credentials.created_at
            )
            
            return True
        except Exception as e:
            print(f"Error storing credentials: {e}")
            return False
    
    async def get_oauth_authorization_url(
        self, 
        service_name: str, 
        scopes: List[str],
        user_id: str
    ) -> str:
        """Generate OAuth2 authorization URL for a service."""
        registry = await self.get_integration_registry()
        service_config = registry.get_service(service_name)
        
        if not service_config:
            raise ValueError(f"Service {service_name} not found in registry")
        
        if service_config.auth_type != "oauth2":
            raise ValueError(f"Service {service_name} does not use OAuth2")
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        
        # Store state in database temporarily
        await self._store_oauth_state(user_id, service_name, state)
        
        # Build authorization URL based on service
        if service_name.startswith("google_"):
            client_id = getattr(settings, f"{service_name}_client_id")
            redirect_uri = f"http://localhost:8000/api/v1/integrations/oauth/callback/{service_name}"
            
            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(scopes),
                "response_type": "code",
                "state": state,
                "access_type": "offline",
                "prompt": "consent"
            }
            
            return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        
        elif service_name == "slack":
            client_id = settings.slack_client_id
            redirect_uri = f"http://localhost:8000/api/v1/integrations/oauth/callback/slack"
            
            params = {
                "client_id": client_id,
                "scope": ",".join(scopes),
                "redirect_uri": redirect_uri,
                "state": state
            }
            
            return f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"
        
        elif service_name == "twitter":
            # Twitter OAuth2 implementation would go here
            raise NotImplementedError("Twitter OAuth2 not yet implemented")
        
        else:
            raise ValueError(f"OAuth2 not implemented for service: {service_name}")
    
    async def _store_oauth_state(self, user_id: str, service_name: str, state: str):
        """Store OAuth state temporarily for verification."""
        # In a real implementation, you'd store this in Redis or a temporary table
        # For now, we'll skip this step
        pass
    
    async def test_integration(
        self, 
        user_id: str, 
        test: IntegrationTest
    ) -> IntegrationTestResult:
        """Test an integration to verify it's working."""
        start_time = time.time()
        
        try:
            registry = await self.get_integration_registry()
            service_config = registry.get_service(test.service_name)
            
            if not service_config:
                return IntegrationTestResult(
                    service_name=test.service_name,
                    test_type=test.test_type,
                    success=False,
                    response_time=time.time() - start_time,
                    error_message=f"Service {test.service_name} not found in registry"
                )
            
            # Get user credentials for this service
            user_integrations = await self.get_user_integrations(user_id)
            user_integration = next(
                (i for i in user_integrations if i.service_name == test.service_name),
                None
            )
            
            if not user_integration and test.test_type != "connection":
                return IntegrationTestResult(
                    service_name=test.service_name,
                    test_type=test.test_type,
                    success=False,
                    response_time=time.time() - start_time,
                    error_message=f"No credentials found for {test.service_name}"
                )
            
            # Perform the test based on service and test type
            success, error_message = await self._perform_service_test(
                service_config, user_integration, test
            )
            
            return IntegrationTestResult(
                service_name=test.service_name,
                test_type=test.test_type,
                success=success,
                response_time=time.time() - start_time,
                error_message=error_message
            )
            
        except Exception as e:
            return IntegrationTestResult(
                service_name=test.service_name,
                test_type=test.test_type,
                success=False,
                response_time=time.time() - start_time,
                error_message=str(e)
            )
    
    async def _perform_service_test(
        self,
        service_config: IntegrationConfig,
        user_integration: Optional[IntegrationCredentials],
        test: IntegrationTest
    ) -> tuple[bool, Optional[str]]:
        """Perform the actual service test."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            if test.test_type == "connection":
                # Test basic connectivity
                try:
                    response = await client.get(service_config.base_url)
                    return response.status_code < 500, None
                except Exception as e:
                    return False, str(e)
            
            elif test.test_type == "auth":
                # Test authentication
                if not user_integration:
                    return False, "No credentials available"
                
                # Test based on service type
                if service_config.service_name == "openai":
                    headers = {
                        "Authorization": f"Bearer {user_integration.credentials.get('api_key')}"
                    }
                    try:
                        response = await client.get(
                            f"{service_config.base_url}/models",
                            headers=headers
                        )
                        return response.status_code == 200, None
                    except Exception as e:
                        return False, str(e)
                
                elif service_config.service_name.startswith("google_"):
                    headers = {
                        "Authorization": f"Bearer {user_integration.credentials.get('access_token')}"
                    }
                    try:
                        # Test with a simple API call
                        if service_config.service_name == "google_drive":
                            response = await client.get(
                                f"{service_config.base_url}/about",
                                headers=headers
                            )
                        else:
                            response = await client.get(
                                service_config.base_url,
                                headers=headers
                            )
                        return response.status_code == 200, None
                    except Exception as e:
                        return False, str(e)
                
                else:
                    return False, f"Auth test not implemented for {service_config.service_name}"
            
            elif test.test_type == "capability":
                # Test specific capability
                return False, "Capability testing not yet implemented"
            
            else:
                return False, f"Unknown test type: {test.test_type}"


async def get_integration_service() -> IntegrationService:
    """Get integration service instance."""
    from src.services.database import get_db
    async with get_db() as db:
        return IntegrationService(db)