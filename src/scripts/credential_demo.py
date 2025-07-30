#!/usr/bin/env python3
"""
Credential Management Demo Script

This script demonstrates how to use the credential management system
to securely store and retrieve API keys and OAuth tokens for various services.
"""

import os
import sys
import asyncio
import json
from typing import Dict, Any, Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.services.credential_manager import CredentialManager
from src.services.database import DatabaseService
from src.config import settings


async def demo_credential_management():
    """Demonstrate credential management features."""
    print("=" * 60)
    print("🔐 Credential Management System Demo")
    print("=" * 60)
    
    # Initialize database connection
    print("\n📦 Initializing database connection...")
    db = DatabaseService()
    await db.connect(settings.database_url)
    
    # Initialize credential manager
    print("🔑 Initializing credential manager...")
    credential_manager = CredentialManager(db)
    
    # Demo user ID
    user_id = "demo-user-123"
    
    # Demo services and credentials
    demo_services = {
        "openai": {
            "api_key": "sk-demo-openai-key-12345",
            "organization": "org-demo-12345"
        },
        "google_drive": {
            "client_id": "demo-google-client-id",
            "client_secret": "demo-google-client-secret",
            "access_token": "demo-google-access-token",
            "refresh_token": "demo-google-refresh-token",
            "token_type": "Bearer",
            "expires_at": 1672531200
        },
        "slack": {
            "client_id": "demo-slack-client-id",
            "client_secret": "demo-slack-client-secret",
            "access_token": "xoxb-demo-slack-access-token",
            "bot_user_id": "U12345678"
        }
    }
    
    # Store credentials for each service
    print("\n📝 Storing credentials for services...")
    for service_name, credentials in demo_services.items():
        print(f"  - {service_name}: ", end="")
        success = await credential_manager.store_credentials(
            user_id=user_id,
            service_name=service_name,
            credentials=credentials,
            configuration={"demo": True, "service_type": service_name.split("_")[0]}
        )
        
        if success:
            print("✅ Success")
        else:
            print("❌ Failed")
    
    # List user integrations
    print("\n📋 Listing user integrations...")
    integrations = await credential_manager.list_user_integrations(user_id)
    
    if integrations:
        print(f"Found {len(integrations)} integrations:")
        for integration in integrations:
            print(f"  - {integration['service_name']} (Status: {integration['status']})")
    else:
        print("No integrations found")
    
    # Retrieve credentials
    print("\n🔍 Retrieving credentials...")
    for service_name in demo_services.keys():
        print(f"  - {service_name}: ", end="")
        credentials = await credential_manager.get_credentials(user_id, service_name)
        
        if credentials:
            # Show a sample of the credentials (first key only)
            first_key = list(credentials.keys())[0]
            value = credentials[first_key]
            masked_value = value[:3] + "*" * (len(value) - 6) + value[-3:] if len(value) > 8 else "********"
            print(f"✅ Success ({first_key}: {masked_value})")
        else:
            print("❌ Failed")
    
    # Update integration status
    print("\n🔄 Updating integration status...")
    service_to_update = "slack"
    print(f"  - Setting {service_to_update} status to 'expired': ", end="")
    success = await credential_manager.update_integration_status(
        user_id=user_id,
        service_name=service_to_update,
        status="expired"
    )
    
    if success:
        print("✅ Success")
    else:
        print("❌ Failed")
    
    # List integrations again to verify status change
    print("\n📋 Listing user integrations after status update...")
    integrations = await credential_manager.list_user_integrations(user_id)
    
    if integrations:
        for integration in integrations:
            print(f"  - {integration['service_name']} (Status: {integration['status']})")
    
    # Delete credentials
    print("\n🗑️ Deleting credentials...")
    service_to_delete = "openai"
    print(f"  - Deleting {service_to_delete} credentials: ", end="")
    success = await credential_manager.delete_credentials(user_id, service_to_delete)
    
    if success:
        print("✅ Success")
    else:
        print("❌ Failed")
    
    # List integrations again to verify deletion
    print("\n📋 Final list of user integrations...")
    integrations = await credential_manager.list_user_integrations(user_id)
    
    if integrations:
        for integration in integrations:
            print(f"  - {integration['service_name']} (Status: {integration['status']})")
    else:
        print("No integrations found")
    
    # Clean up demo data
    print("\n🧹 Cleaning up demo data...")
    for service_name in list(demo_services.keys()):
        await credential_manager.delete_credentials(user_id, service_name)
    
    # Close database connection
    await db.close()
    
    print("\n✅ Demo completed successfully!")
    print("\n💡 Key takeaways:")
    print("  - Credentials are encrypted before storage")
    print("  - Encryption keys are derived from the application secret key")
    print("  - Credentials can be retrieved only by the user who stored them")
    print("  - Integration status can be updated (active, expired, error, etc.)")
    print("  - Credentials can be deleted when no longer needed")


async def main():
    """Main function."""
    try:
        await demo_credential_management()
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        return False
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)