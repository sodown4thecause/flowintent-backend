"""Secure credential management service for the Natural Language Workflow Platform."""

import os
import json
import base64
import hashlib
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..config import settings


class CredentialManager:
    """Manages secure storage and retrieval of user credentials."""
    
    def __init__(self, secret_key: Optional[str] = None):
        """Initialize the credential manager with encryption key."""
        self.secret_key = secret_key or settings.secret_key
        self._fernet = None
    
    def _get_fernet(self) -> Fernet:
        """Get or create the Fernet encryption instance."""
        if self._fernet is None:
            # Derive encryption key from secret key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'workflow_platform_salt',  # In production, use a random salt per user
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self.secret_key.encode()))
            self._fernet = Fernet(key)
        return self._fernet
    
    async def encrypt_credentials(self, credentials: Dict[str, Any]) -> Dict[str, str]:
        """Encrypt user credentials for secure storage."""
        fernet = self._get_fernet()
        
        encrypted_data = {}
        for key, value in credentials.items():
            if value is not None:
                # Convert to string and encrypt
                value_str = str(value)
                encrypted_value = fernet.encrypt(value_str.encode())
                encrypted_data[key] = base64.urlsafe_b64encode(encrypted_value).decode()
        
        return encrypted_data
    
    async def decrypt_credentials(self, encrypted_credentials: Dict[str, str]) -> Dict[str, str]:
        """Decrypt user credentials for use."""
        fernet = self._get_fernet()
        
        decrypted_data = {}
        for key, encrypted_value in encrypted_credentials.items():
            try:
                # Decode and decrypt
                encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
                decrypted_bytes = fernet.decrypt(encrypted_bytes)
                decrypted_data[key] = decrypted_bytes.decode()
            except Exception as e:
                # Log error but don't expose details
                print(f"Error decrypting credential {key}: {e}")
                continue
        
        return decrypted_data
    
    async def hash_credential(self, credential: str) -> str:
        """Create a hash of a credential for comparison without storing the actual value."""
        return hashlib.sha256(credential.encode()).hexdigest()
    
    async def verify_credential_hash(self, credential: str, credential_hash: str) -> bool:
        """Verify a credential against its hash."""
        return hashlib.sha256(credential.encode()).hexdigest() == credential_hash
    
    def mask_credential(self, credential: str, show_chars: int = 4) -> str:
        """Mask a credential for display purposes."""
        if len(credential) <= show_chars:
            return "*" * len(credential)
        return credential[:show_chars] + "*" * (len(credential) - show_chars)


# Global instance
credential_manager = CredentialManager()


async def get_credential_manager() -> CredentialManager:
    """Get the credential manager instance."""
    return credential_manager