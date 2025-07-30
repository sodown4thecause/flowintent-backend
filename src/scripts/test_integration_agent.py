"""Test script for the Integration Agent."""

import os
import sys
import asyncio
import httpx
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.services.database import DatabaseService
from src.services.integration_service import IntegrationService
from src.agents.integration_agent import analyze_integration_requirements
from src.models.integration import IntegrationCredentials


async def setup_services():
    """Set up the required services."""
    print("🔧 Setting up services...")
    
    # Initialize database
    db = await DatabaseService.create()
    
    # Initialize integration service
    integration_service = IntegrationService(db)
    
    return db, integration_service


async def create_test_user(db):
    """Create a test user if it doesn't exist."""
    print("🧑‍💻 Creating test user...")
    
    # Check if test user exists
    query = "SELECT id FROM users WHERE email = $1"
    user = await db.fetchrow(query, "integration_test@example.com")
    
    if user:
        print(f"Test user already exists with ID: {user['id']}")
        return str(user['id'])
    
    # Create test user
    query = """
        INSERT INTO users (email, name, subscription_tier)
        VALUES ($1, $2, $3)
        RETURNING id
    """
    
    user_id = await db.fetchval(
        query,
        "integration_test@example.com",
        "Integration Test User",
        "pro"
    )
    
    print(f"Created test user with ID: {user_id}")
    return str(user_id)


async def test_integration_analysis():
    """Test the integration analysis functionality."""
    print("\n🧠 Testing Integration Analysis\n")
    print("=" * 80)
    
    # Setup services
    db, integration_service = await setup_services()
    user_id = await create_test_user(db)
    
    # Test workflow descriptions
    test_workflows = [
        "Create a workflow that sends a daily email with my Google Calendar events to my Slack channel",
        "Build a workflow that monitors my Twitter mentions and saves them to a Google Sheet",
        "Make a workflow that generates AI summaries of my Google Drive documents and posts them to LinkedIn",
        "Create a workflow that backs up my Slack messages to Dropbox every week"
    ]
    
    async with httpx.AsyncClient() as http_client:
        for i, workflow_description in enumerate(test_workflows):
            print(f"\n📋 Test Workflow #{i+1}:")
            print(f"Description: {workflow_description}")
            print("-" * 60)
            
            try:
                # Analyze integration requirements
                analysis = await analyze_integration_requirements(
                    workflow_description=workflow_description,
                    user_id=user_id,
                    integration_service=integration_service,
                    http_client=http_client
                )
                
                print(f"✅ Analysis completed with confidence: {analysis.confidence:.2f}")
                print(f"🔌 Required services: {', '.join(analysis.required_services)}")
                
                print("\n📋 Capabilities needed:")
                for service, capabilities in analysis.capabilities_needed.items():
                    print(f"  • {service}: {', '.join(capabilities)}")
                
                print("\n🔐 Authentication requirements:")
                for service, auth_type in analysis.auth_requirements.items():
                    print(f"  • {service}: {auth_type}")
                
                if analysis.setup_instructions:
                    print("\n📝 Setup instructions:")
                    for j, instruction in enumerate(analysis.setup_instructions, 1):
                        print(f"  {j}. {instruction}")
                
                if analysis.missing_integrations:
                    print(f"\n⚠️  Missing integrations: {', '.join(analysis.missing_integrations)}")
                
            except Exception as e:
                print(f"❌ Error analyzing workflow: {e}")
            
            print("\n" + "=" * 80)
    
    await db.close()


async def test_integration_registry():
    """Test the integration registry functionality."""
    print("\n📚 Testing Integration Registry\n")
    print("=" * 80)
    
    # Setup services
    db, integration_service = await setup_services()
    
    try:
        # Get integration registry
        registry = await integration_service.get_integration_registry()
        
        print(f"✅ Registry loaded with {len(registry.services)} services")
        
        print("\n🔌 Available services:")
        for service_name, config in registry.services.items():
            print(f"\n• {service_name.upper()}")
            print(f"  Auth Type: {config.auth_type}")
            print(f"  Capabilities: {', '.join(config.capabilities)}")
            print(f"  Base URL: {config.base_url}")
            if config.required_scopes:
                print(f"  Required Scopes: {', '.join(config.required_scopes)}")
        
        # Test service lookup
        print(f"\n🔍 Testing service lookup...")
        google_drive = registry.get_service("google_drive")
        if google_drive:
            print(f"✅ Found Google Drive service with {len(google_drive.capabilities)} capabilities")
        
        # Test capability search
        email_services = registry.get_services_by_capability("send_email")
        print(f"✅ Found {len(email_services)} services that can send emails")
        
    except Exception as e:
        print(f"❌ Error testing registry: {e}")
    
    await db.close()


async def test_credential_storage():
    """Test credential storage and retrieval."""
    print("\n🔐 Testing Credential Storage\n")
    print("=" * 80)
    
    # Setup services
    db, integration_service = await setup_services()
    user_id = await create_test_user(db)
    
    try:
        # Test storing API key credentials
        print("💾 Testing API key storage...")
        
        openai_credentials = IntegrationCredentials(
            user_id=user_id,
            service_name="openai",
            auth_type="api_key",
            credentials={
                "api_key": "sk-test-key-12345",
                "organization": "org-test"
            }
        )
        
        success = await integration_service.store_credentials(openai_credentials)
        if success:
            print("✅ OpenAI credentials stored successfully")
        else:
            print("❌ Failed to store OpenAI credentials")
        
        # Test retrieving credentials
        print("\n📥 Testing credential retrieval...")
        
        user_integrations = await integration_service.get_user_integrations(user_id)
        print(f"✅ Retrieved {len(user_integrations)} integrations for user")
        
        for integration in user_integrations:
            print(f"  • {integration.service_name} ({integration.auth_type}) - Status: {integration.status}")
        
    except Exception as e:
        print(f"❌ Error testing credential storage: {e}")
    
    await db.close()


async def main():
    """Run all integration agent tests."""
    print("🚀 Starting Integration Agent Tests")
    
    try:
        # Test integration analysis
        await test_integration_analysis()
        
        # Test integration registry
        await test_integration_registry()
        
        # Test credential storage
        await test_credential_storage()
        
        print("\n🎉 All integration agent tests completed!")
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)