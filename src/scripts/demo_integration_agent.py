"""Demo script for the Integration Agent with Cerebras support."""

import os
import sys
import asyncio
import httpx
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.services.integration_service import IntegrationService
from src.services.database import DatabaseService
from src.agents.integration_agent import analyze_integration_requirements
from src.models.integration import IntegrationCredentials


async def setup_services():
    """Set up the required services."""
    print("🔧 Setting up services...")
    
    # Initialize database
    print("Connecting to database...")
    db = await DatabaseService.create()
    
    # Initialize integration service
    print("Initializing integration service...")
    integration_service = IntegrationService(db)
    
    return db, integration_service


async def demo_cerebras_integration(integration_service: IntegrationService):
    """Demo Cerebras integration setup."""
    print("\n🧠 Setting up Cerebras integration...")
    
    # Store Cerebras credentials
    cerebras_creds = IntegrationCredentials(
        user_id="demo-user",
        service_name="cerebras",
        auth_type="api_key",
        credentials={
            "api_key": "csk-xthxntm32x8kd5hdvfp4h3xk2vcnwtf2k2c9r8mtc8w2vvf2",
            "auth_type": "api_key"
        }
    )
    
    success = await integration_service.store_credentials(cerebras_creds)
    if success:
        print("✅ Cerebras credentials stored successfully")
    else:
        print("❌ Failed to store Cerebras credentials")
    
    # Test the integration
    from src.models.integration import IntegrationTest
    test = IntegrationTest(
        service_name="cerebras",
        test_type="connection"
    )
    
    result = await integration_service.test_integration("demo-user", test)
    print(f"🧪 Cerebras connection test: {'✅ PASSED' if result.success else '❌ FAILED'}")
    if not result.success:
        print(f"   Error: {result.error_message}")
    print(f"   Response time: {result.response_time:.2f}s")


async def demo_integration_analysis():
    """Demo integration requirement analysis."""
    print("\n🔍 Analyzing integration requirements...")
    
    # Setup services
    db, integration_service = await setup_services()
    
    # Demo Cerebras setup
    await demo_cerebras_integration(integration_service)
    
    # Test workflow descriptions
    test_workflows = [
        "Create a workflow that posts daily AI news summaries to Slack",
        "Build a workflow that backs up Google Drive files to Dropbox every week",
        "Make a workflow that sends personalized emails to customers based on their purchase history",
        "Create a workflow that monitors Twitter mentions and responds automatically",
        "Build a workflow that generates weekly reports from Google Sheets data and emails them"
    ]
    
    async with httpx.AsyncClient() as http_client:
        for i, workflow_desc in enumerate(test_workflows):
            print(f"\n📋 Workflow #{i+1}: {workflow_desc}")
            print("=" * 80)
            
            try:
                analysis = await analyze_integration_requirements(
                    workflow_description=workflow_desc,
                    user_id="demo-user",
                    integration_service=integration_service,
                    http_client=http_client
                )
                
                print(f"🎯 Required Services: {', '.join(analysis.required_services)}")
                print(f"🔧 Capabilities Needed:")
                for service, capabilities in analysis.capabilities_needed.items():
                    print(f"   - {service}: {', '.join(capabilities)}")
                
                print(f"🔐 Auth Requirements:")
                for service, auth_type in analysis.auth_requirements.items():
                    print(f"   - {service}: {auth_type}")
                
                print(f"📝 Setup Instructions:")
                for instruction in analysis.setup_instructions:
                    print(f"   • {instruction}")
                
                if analysis.missing_integrations:
                    print(f"⚠️  Missing Integrations: {', '.join(analysis.missing_integrations)}")
                
                print(f"🎯 Confidence: {analysis.confidence:.2f}")
                
            except Exception as e:
                print(f"❌ Error analyzing workflow: {e}")
            
            print("\n" + "=" * 80)
    
    # Test integration registry
    print("\n📚 Available Integrations:")
    registry = await integration_service.get_integration_registry()
    
    for service_name, config in registry.services.items():
        print(f"\n🔌 {service_name.title()}")
        print(f"   Auth Type: {config.auth_type}")
        print(f"   Capabilities: {', '.join(config.capabilities)}")
        print(f"   Base URL: {config.base_url}")
        if config.rate_limits:
            print(f"   Rate Limits: {config.rate_limits}")
    
    # Cleanup
    await db.close()
    
    print("\n🎉 Integration Agent demo completed!")


async def main():
    """Main function."""
    try:
        print("🚀 Starting Integration Agent Demo with Cerebras")
        print("=" * 60)
        
        await demo_integration_analysis()
        
        return True
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)