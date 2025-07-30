"""
Script to import n8n workflow templates into our platform.
"""
import asyncio
import os
import json
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import services
from src.services.database import DatabaseService
from src.services.vector_store import VectorStoreService
from src.services.template_service import TemplateService

async def import_n8n_templates():
    """Import n8n workflow templates into our platform."""
    print("Starting n8n template import...")
    
    # Initialize services
    db_service = await DatabaseService.create()
    vector_store = VectorStoreService()
    await vector_store.initialize()
    
    # Create template service
    template_service = TemplateService(db_service.pool, vector_store)
    
    # Source directory for n8n templates
    source_dir = "json templates"
    
    # Check if source directory exists
    if not os.path.exists(source_dir):
        print(f"Source directory '{source_dir}' not found")
        return
    
    # Create target directory if it doesn't exist
    target_dir = "src/templates/workflow_templates"
    os.makedirs(target_dir, exist_ok=True)
    
    # Copy templates to target directory
    for filename in os.listdir(source_dir):
        if not filename.endswith('.json'):
            continue
            
        source_path = os.path.join(source_dir, filename)
        target_path = os.path.join(target_dir, filename)
        
        # Copy file
        shutil.copy2(source_path, target_path)
        print(f"Copied {filename} to {target_dir}")
    
    # Import templates into database
    count = await template_service.seed_templates_from_directory(source_dir)
    print(f"Successfully imported {count} n8n templates into the database")
    
    # Close connections
    await db_service.close()
    await vector_store.close()
    
    print("n8n template import completed successfully")

if __name__ == "__main__":
    # Run import
    asyncio.run(import_n8n_templates())