"""Demo script to showcase the Natural Language Workflow Platform."""

import os
import sys
import asyncio
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.services.vector_store import VectorStoreService
from src.services.workflow_service import WorkflowService
from src.services.database import DatabaseService
from src.agents.intent_parser import parse_intent
from src.agents.workflow_builder import build_workflow
from src.agents.orchestrator import handle_user_input, PlatformState


async def setup_services():
    """Set up the required services."""
    print("🔧 Setting up services...")
    
    # Initialize database
    print("Connecting to database...")
    db = DatabaseService()
    db = await DatabaseService.create()
    
    # Initialize vector store
    print("Initializing vector store...")
    vector_store = VectorStoreService()
    await vector_store.initialize()
    
    # Initialize workflow service
    print("Initializing workflow service...")
    workflow_service = WorkflowService(db)
    
    return db, vector_store, workflow_service


async def create_demo_user(db):
    """Create a demo user if it doesn't exist."""
    print("🧑‍💻 Creating demo user...")
    
    # Check if demo user exists
    query = "SELECT id FROM users WHERE email = $1"
    user = await db.fetchrow(query, "demo@example.com")
    
    if user:
        print(f"Demo user already exists with ID: {user['id']}")
        return user['id']
    
    # Create demo user
    query = """
        INSERT INTO users (email, name, subscription_tier)
        VALUES ($1, $2, $3)
        RETURNING id
    """
    
    user_id = await db.fetchval(
        query,
        "demo@example.com",
        "Demo User",
        "pro"
    )
    
    print(f"Created demo user with ID: {user_id}")
    return user_id


async def run_demo(user_id, vector_store, workflow_service):
    """Run the demo workflow creation."""
    print("\n🚀 Starting Natural Language Workflow Platform Demo\n")
    
    # Initialize platform state
    state = PlatformState(
        user_id=user_id,
        conversation_id=str(uuid.uuid4())
    )
    
    # Demo workflow descriptions
    demo_workflows = [
        "Create a workflow that sends me a daily email with the top 5 news articles about artificial intelligence",
        "Build a workflow that monitors my Google Drive for new files and backs them up to Dropbox",
        "Create a workflow that posts a daily weather forecast to my Slack channel every morning at 8 AM",
        "Make a workflow that analyzes my Twitter mentions and sends me a weekly summary report"
    ]
    
    # Process each workflow
    for i, description in enumerate(demo_workflows):
        print(f"\n📋 Demo Workflow #{i+1}: {description}\n")
        print("=" * 80)
        
        print("\n🧠 Parsing intent...\n")
        intent_result = await parse_intent(
            user_input=description,
            vector_store=vector_store,
            user_id=user_id
        )
        
        print(f"✅ Intent parsed with confidence: {intent_result.confidence:.2f}")
        print(f"🎯 Goal: {intent_result.intent.goal}")
        print(f"🔌 Required integrations: {', '.join(intent_result.intent.integrations)}")
        
        print("\n🛠️ Building workflow...\n")
        workflow_result = await build_workflow(
            intent=intent_result.intent,
            vector_store=vector_store,
            user_id=user_id
        )
        
        print(f"✅ Workflow built: {workflow_result.workflow.name}")
        print(f"⏱️ Estimated runtime: {workflow_result.estimated_runtime} seconds")
        print(f"📝 Description: {workflow_result.workflow.description}")
        
        print("\n📊 Workflow steps:")
        for j, step in enumerate(workflow_result.workflow.steps):
            print(f"  {j+1}. {step.name} ({step.type}) - Service: {step.service}")
            if step.dependencies:
                print(f"     Dependencies: {', '.join(step.dependencies)}")
        
        # Store workflow in vector database
        print("\n💾 Storing workflow in vector database...")
        await vector_store.store(
            id=workflow_result.workflow.id,
            content={
                "id": workflow_result.workflow.id,
                "name": workflow_result.workflow.name,
                "description": workflow_result.workflow.description,
                "steps": [step.dict() for step in workflow_result.workflow.steps],
                "estimated_runtime": workflow_result.workflow.estimated_runtime
            },
            collection_type="workflows"
        )
        
        print("\n" + "=" * 80)
    
    # Demo similar workflow search
    print("\n🔍 Demonstrating similar workflow search...\n")
    
    search_query = "Create a workflow for social media posting"
    print(f"Search query: '{search_query}'")
    
    results = await vector_store.search(
        query=search_query,
        collection_type="workflows",
        limit=3
    )
    
    print(f"\nFound {len(results)} similar workflows:")
    for i, result in enumerate(results):
        print(f"\n{i+1}. {result.content.get('name')} (Score: {result.score:.2f})")
        print(f"   {result.content.get('description')}")
    
    print("\n🎉 Demo completed successfully!")


async def main():
    """Main function."""
    try:
        # Setup services
        db, vector_store, workflow_service = await setup_services()
        
        # Create demo user
        user_id = await create_demo_user(db)
        
        # Run demo
        await run_demo(user_id, vector_store, workflow_service)
        
        # Cleanup
        await vector_store.close()
        await db.close()
        
        return True
    except Exception as e:
        print(f"❌ Error running demo: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)