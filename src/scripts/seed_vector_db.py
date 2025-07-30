"""Script to seed the vector database with sample workflows and templates."""

import os
import sys
import asyncio
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.services.vector_store import VectorStoreService
from src.models.workflow import ExecutableWorkflow, WorkflowStep


# Sample workflow templates
SAMPLE_WORKFLOWS = [
    {
        "id": "email-automation-workflow",
        "name": "Email Automation Workflow",
        "description": "Automatically send personalized emails based on triggers like new sign-ups or customer actions.",
        "steps": [
            {
                "id": "trigger-step",
                "name": "Monitor for New Events",
                "type": "trigger",
                "service": "webhook",
                "configuration": {
                    "event_type": "new_signup",
                    "webhook_url": "/api/webhooks/new-signup"
                },
                "dependencies": []
            },
            {
                "id": "data-step",
                "name": "Fetch User Data",
                "type": "action",
                "service": "database",
                "configuration": {
                    "query_type": "user_details",
                    "parameters": {"user_id": "{{trigger.user_id}}"}
                },
                "dependencies": ["trigger-step"]
            },
            {
                "id": "template-step",
                "name": "Generate Email Content",
                "type": "transform",
                "service": "template",
                "configuration": {
                    "template_id": "welcome-email",
                    "variables": {
                        "name": "{{data.user_name}}",
                        "company": "{{data.company_name}}"
                    }
                },
                "dependencies": ["data-step"]
            },
            {
                "id": "email-step",
                "name": "Send Email",
                "type": "action",
                "service": "email",
                "configuration": {
                    "to": "{{data.email}}",
                    "subject": "Welcome to Our Service",
                    "body": "{{template.content}}",
                    "from": "support@example.com"
                },
                "dependencies": ["template-step"]
            }
        ],
        "estimated_runtime": 30
    },
    {
        "id": "social-media-scheduler",
        "name": "Social Media Content Scheduler",
        "description": "Schedule and post content across multiple social media platforms automatically.",
        "steps": [
            {
                "id": "content-step",
                "name": "Prepare Content",
                "type": "transform",
                "service": "content",
                "configuration": {
                    "content_type": "social_post",
                    "parameters": {"topic": "{{workflow.topic}}"}
                },
                "dependencies": []
            },
            {
                "id": "image-step",
                "name": "Generate Image",
                "type": "action",
                "service": "openai",
                "configuration": {
                    "model": "dall-e-3",
                    "prompt": "{{content.summary}}",
                    "size": "1024x1024"
                },
                "dependencies": ["content-step"]
            },
            {
                "id": "twitter-step",
                "name": "Post to Twitter",
                "type": "action",
                "service": "twitter",
                "configuration": {
                    "text": "{{content.twitter_text}}",
                    "media": ["{{image.url}}"]
                },
                "dependencies": ["content-step", "image-step"]
            },
            {
                "id": "linkedin-step",
                "name": "Post to LinkedIn",
                "type": "action",
                "service": "linkedin",
                "configuration": {
                    "text": "{{content.linkedin_text}}",
                    "media": ["{{image.url}}"]
                },
                "dependencies": ["content-step", "image-step"]
            }
        ],
        "estimated_runtime": 120
    },
    {
        "id": "data-analysis-workflow",
        "name": "Data Analysis and Reporting",
        "description": "Automatically fetch data from various sources, analyze it, and generate reports.",
        "steps": [
            {
                "id": "schedule-step",
                "name": "Schedule Trigger",
                "type": "trigger",
                "service": "schedule",
                "configuration": {
                    "cron": "0 9 * * 1",  # Every Monday at 9 AM
                    "timezone": "UTC"
                },
                "dependencies": []
            },
            {
                "id": "fetch-data-step",
                "name": "Fetch Data from API",
                "type": "action",
                "service": "http",
                "configuration": {
                    "url": "https://api.example.com/data",
                    "method": "GET",
                    "headers": {
                        "Authorization": "Bearer {{secrets.API_KEY}}"
                    }
                },
                "dependencies": ["schedule-step"]
            },
            {
                "id": "analyze-step",
                "name": "Analyze Data",
                "type": "transform",
                "service": "python",
                "configuration": {
                    "code": "import pandas as pd\ndf = pd.DataFrame(input_data)\nresult = df.groupby('category').sum().to_dict()",
                    "input": "{{fetch-data-step.response.body}}"
                },
                "dependencies": ["fetch-data-step"]
            },
            {
                "id": "report-step",
                "name": "Generate Report",
                "type": "transform",
                "service": "template",
                "configuration": {
                    "template_id": "monthly-report",
                    "variables": {
                        "data": "{{analyze-step.result}}",
                        "date": "{{workflow.execution_date}}"
                    }
                },
                "dependencies": ["analyze-step"]
            },
            {
                "id": "email-report-step",
                "name": "Email Report",
                "type": "action",
                "service": "email",
                "configuration": {
                    "to": ["reports@example.com"],
                    "subject": "Monthly Data Report - {{workflow.execution_date}}",
                    "body": "{{report-step.content}}",
                    "attachments": ["{{report-step.pdf}}"]
                },
                "dependencies": ["report-step"]
            }
        ],
        "estimated_runtime": 300
    }
]


async def seed_vector_db():
    """Seed the vector database with sample workflows."""
    print("🌱 Seeding vector database with sample workflows...")
    
    # Initialize vector store
    vector_store = VectorStoreService()
    await vector_store.initialize()
    
    # Convert sample workflows to ExecutableWorkflow objects
    workflows = []
    for workflow_data in SAMPLE_WORKFLOWS:
        # Convert steps to WorkflowStep objects
        steps = [WorkflowStep(**step) for step in workflow_data["steps"]]
        
        # Create ExecutableWorkflow
        workflow = ExecutableWorkflow(
            id=workflow_data["id"],
            name=workflow_data["name"],
            description=workflow_data["description"],
            steps=steps,
            estimated_runtime=workflow_data["estimated_runtime"]
        )
        
        workflows.append(workflow)
    
    # Store workflows in vector database
    for workflow in workflows:
        print(f"Storing workflow: {workflow.name}")
        
        # Store in workflows collection
        success = await vector_store.store(
            id=workflow.id,
            content={
                "id": workflow.id,
                "name": workflow.name,
                "description": workflow.description,
                "steps": [step.dict() for step in workflow.steps],
                "estimated_runtime": workflow.estimated_runtime
            },
            collection_type="workflows"
        )
        
        if success:
            print(f"✅ Stored workflow: {workflow.name}")
        else:
            print(f"❌ Failed to store workflow: {workflow.name}")
    
    # Store individual steps in steps collection
    for workflow in workflows:
        for step in workflow.steps:
            print(f"Storing step: {step.name}")
            
            # Store in steps collection
            success = await vector_store.store(
                id=f"{workflow.id}-{step.id}",
                content={
                    "id": step.id,
                    "name": step.name,
                    "type": step.type,
                    "service": step.service,
                    "workflow_id": workflow.id,
                    "workflow_name": workflow.name,
                    "configuration": step.configuration,
                    "dependencies": step.dependencies
                },
                collection_type="steps"
            )
            
            if success:
                print(f"✅ Stored step: {step.name}")
            else:
                print(f"❌ Failed to store step: {step.name}")
    
    print("✅ Vector database seeding complete!")


async def main():
    """Main function."""
    try:
        await seed_vector_db()
        return True
    except Exception as e:
        print(f"❌ Error seeding vector database: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)