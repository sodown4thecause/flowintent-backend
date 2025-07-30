"""Authentication management for integrations."""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlencode, parse_qs
import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .config import AuthType, OAuthConfig, APIKeyConfig, BasicAuthConfig
from ..config import settings
from ..errors import AuthenticationError
from ..services.database import DatabaseService

logger = logging.getLogger(__name__)


class AuthenticationManager:
    """Manager for handling authentication across integrations."""
    
    def __init__(self, db: Optional[DatabaseService] = None):
        self.db = db
        self._encryption_key = self._derive_encryption_key()
        self._fernet = Fernet(self._encryption_key)
        self.oauth_handlers: Dict[str, 'OAuthHandler'] = {}
        self.api_key_handlers: Dict[str, 'APIKeyHandler'] = {}
    
    def _derive_encryption_key(self) -> bytes:
        """Derive encryption key from application secret."""
        password = settings.secret_key.encode()
        salt = b'workflow_platform_salt'  # In production, use a random salt per installation
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def _encrypt_data(self, data: str) -> str:
        """Encrypt sensitive data."""
        return self._fernet.encrypt(data.encode()).decode()
    
    def _decrypt_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data."""
        return self._fernet.decrypt(encrypted_data.encode()).decode()
    
    async def store_credentials(
        self,
        service_name: str,
        user_id: str,
        credentials: Dict[str, Any],
        auth_type: AuthType
    ) -> bool:
        """Store encrypted credentials for a service."""
        try:
            # Encrypt the credentials
            encrypted_credentials = self._encrypt_data(json.dumps(credentials))
            
            # Store in database
            if self.db:
                query = """
                    INSERT INTO user_integrations (user_id, service_name, auth_data, status, created_at)
                    VALUES ($1, $2, $3, 'active', NOW())
                    ON CONFLICT (user_id, service_name)
                    DO UPDATE SET auth_data = $3, status = 'active', last_used = NOW()
                """
                
                await self.db.execute(
                    query,
                    user_id,
                    service_name,
                    json.dumps({"encrypted": encrypted_credentials, "auth_type": auth_type.value})
                )
            
            logger.info(f"Stored credentials for {service_name}:{user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to store credentials for {service_name}: {e}")
            raise AuthenticationError(
                f"Failed to store credentials: {str(e)}",
                service=service_name
            )
    
    async def get_credentials(
        self,
        service_name: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get decrypted credentials for a service."""
        try:
            if not self.db:
                return None
            
            query = """
                SELECT auth_data FROM user_integrations
                WHERE user_id = $1 AND service_name = $2 AND status = 'active'
            """
            
            row = await self.db.fetchrow(query, user_id, service_name)
            if not row:
                return None
            
            auth_data = json.loads(row['auth_data'])
            encrypted_credentials = auth_data.get('encrypted')
            
            if not encrypted_credentials:
                return None
            
            # Decrypt credentials
            decrypted_data = self._decrypt_data(encrypted_credentials)
            credentials = json.loads(decrypted_data)
            
            return credentials
        
        except Exception as e:
            logger.error(f"Failed to get credentials for {service_name}: {e}")
            return None
    
    async def remove_credentials(self, service_name: str, user_id: str) -> bool:
        """Remove credentials for a service."""
        try:
            if not self.db:
                return False
            
            query = """
                UPDATE user_integrations 
                SET status = 'removed', auth_data = '{}'
                WHERE user_id = $1 AND service_name = $2
            """
            
            await self.db.execute(query, user_id, service_name)
            logger.info(f"Removed credentials for {service_name}:{user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to remove credentials for {service_name}: {e}")
            return False
    
    async def get_authentication(
        self,
        service_name: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get authentication headers/data for API requests."""
        credentials = await self.get_credentials(service_name, user_id)
        if not credentials:
            return None
        
        # Get auth type from stored data
        if self.db:
            query = """
                SELECT auth_data FROM user_integrations
                WHERE user_id = $1 AND service_name = $2 AND status = 'active'
            """
            row = await self.db.fetchrow(query, user_id, service_name)
            if row:
                auth_data = json.loads(row['auth_data'])
                auth_type = AuthType(auth_data.get('auth_type', 'api_key'))
            else:
                auth_type = AuthType.API_KEY
        else:
            auth_type = AuthType.API_KEY
        
        # Generate authentication based on type
        if auth_type == AuthType.API_KEY:
            return self._create_api_key_auth(credentials)
        elif auth_type == AuthType.BEARER_TOKEN:
            return self._create_bearer_token_auth(credentials)
        elif auth_type == AuthType.OAUTH2:
            return await self._create_oauth2_auth(credentials, service_name, user_id)
        elif auth_type == AuthType.BASIC_AUTH:
            return self._create_basic_auth(credentials)
        else:
            return credentials
    
    def _create_api_key_auth(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Create API key authentication."""
        api_key = credentials.get('api_key')
        key_name = credentials.get('key_name', 'X-API-Key')
        key_location = credentials.get('key_location', 'header')
        key_prefix = credentials.get('key_prefix', '')
        
        if not api_key:
            return {}
        
        value = f"{key_prefix}{api_key}" if key_prefix else api_key
        
        if key_location == 'header':
            return {'headers': {key_name: value}}
        elif key_location == 'query':
            return {'params': {key_name: value}}
        else:
            return {'data': {key_name: value}}
    
    def _create_bearer_token_auth(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Create Bearer token authentication."""
        token = credentials.get('access_token') or credentials.get('token')
        if not token:
            return {}
        
        return {'headers': {'Authorization': f'Bearer {token}'}}
    
    async def _create_oauth2_auth(
        self,
        credentials: Dict[str, Any],
        service_name: str,
        user_id: str
    ) -> Dict[str, Any]:
        """Create OAuth2 authentication, refreshing token if needed."""
        access_token = credentials.get('access_token')
        refresh_token = credentials.get('refresh_token')
        expires_at = credentials.get('expires_at')
        
        if not access_token:
            return {}
        
        # Check if token needs refresh
        if expires_at and datetime.fromtimestamp(expires_at) <= datetime.now():
            if refresh_token:
                # Try to refresh the token
                new_credentials = await self._refresh_oauth2_token(
                    service_name, refresh_token, credentials
                )
                if new_credentials:
                    # Store updated credentials
                    await self.store_credentials(
                        service_name, user_id, new_credentials, AuthType.OAUTH2
                    )
                    access_token = new_credentials['access_token']
        
        return {'headers': {'Authorization': f'Bearer {access_token}'}}
    
    def _create_basic_auth(self, credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Create Basic authentication."""
        username = credentials.get('username')
        password = credentials.get('password')
        
        if not username or not password:
            return {}
        
        # Encode credentials
        credentials_str = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials_str.encode()).decode()
        
        return {'headers': {'Authorization': f'Basic {encoded_credentials}'}}
    
    async def _refresh_oauth2_token(
        self,
        service_name: str,
        refresh_token: str,
        current_credentials: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Refresh an OAuth2 access token."""
        try:
            # This would need service-specific token refresh URLs
            # For now, return None to indicate refresh failed
            logger.warning(f"Token refresh not implemented for {service_name}")
            return None
        
        except Exception as e:
            logger.error(f"Failed to refresh token for {service_name}: {e}")
            return None


class OAuthHandler:
    """Handler for OAuth2 authentication flows."""
    
    def __init__(self, config: OAuthConfig):
        self.config = config
        self.pending_states: Dict[str, Dict[str, Any]] = {}
    
    def generate_authorization_url(self, user_id: str) -> Tuple[str, str]:
        """Generate authorization URL and state for OAuth flow."""
        state = secrets.token_urlsafe(32)
        
        # Store state for verification
        self.pending_states[state] = {
            'user_id': user_id,
            'created_at': datetime.now(),
            'service': self.config.client_id  # Use client_id as service identifier
        }
        
        params = {
            'client_id': self.config.client_id,
            'redirect_uri': self.config.redirect_uri,
            'scope': ' '.join(self.config.scopes),
            'state': state,
            'response_type': 'code'
        }
        
        # Add additional parameters
        params.update(self.config.additional_params)
        
        auth_url = f"{self.config.authorization_url}?{urlencode(params)}"
        return auth_url, state
    
    async def handle_callback(
        self,
        code: str,
        state: str,
        error: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Handle OAuth callback and exchange code for tokens."""
        if error:
            raise AuthenticationError(f"OAuth error: {error}")
        
        # Verify state
        if state not in self.pending_states:
            raise AuthenticationError("Invalid OAuth state")
        
        state_data = self.pending_states.pop(state)
        
        # Check state expiry (5 minutes)
        if datetime.now() - state_data['created_at'] > timedelta(minutes=5):
            raise AuthenticationError("OAuth state expired")
        
        try:
            # Exchange code for tokens
            async with httpx.AsyncClient() as client:
                token_data = {
                    'client_id': self.config.client_id,
                    'client_secret': self.config.client_secret,
                    'code': code,
                    'redirect_uri': self.config.redirect_uri,
                    'grant_type': 'authorization_code'
                }
                
                response = await client.post(
                    self.config.token_url,
                    data=token_data,
                    headers={'Accept': 'application/json'}
                )
                
                if response.status_code != 200:
                    raise AuthenticationError(f"Token exchange failed: {response.text}")
                
                tokens = response.json()
                
                # Calculate expiry time
                expires_in = tokens.get('expires_in')
                expires_at = None
                if expires_in:
                    expires_at = (datetime.now() + timedelta(seconds=expires_in)).timestamp()
                
                return {
                    'access_token': tokens['access_token'],
                    'refresh_token': tokens.get('refresh_token'),
                    'token_type': tokens.get('token_type', 'Bearer'),
                    'expires_at': expires_at,
                    'scope': tokens.get('scope'),
                    'user_id': state_data['user_id']
                }
        
        except Exception as e:
            logger.error(f"OAuth callback error: {e}")
            raise AuthenticationError(f"OAuth callback failed: {str(e)}")


class APIKeyHandler:
    """Handler for API key authentication."""
    
    def __init__(self, config: APIKeyConfig):
        self.config = config
    
    def create_auth_data(self, api_key: str) -> Dict[str, Any]:
        """Create authentication data for API key."""
        return {
            'api_key': api_key,
            'key_name': self.config.key_name,
            'key_location': self.config.key_location,
            'key_prefix': self.config.key_prefix
        }