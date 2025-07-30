"""
Script to set up database tables for workflow templates.
"""
import asyncio
import asyncpg
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def setup_template_tables():
    """Set up database tables for workflow templates."""
    # Get database connection string from environment
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("DATABASE_URL environment variable not set")
        return
    
    # Connect to database
    conn = await asyncpg.connect(db_url)
    
    try:
        # Create workflow_templates table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_templates (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            category VARCHAR(100) NOT NULL,
            tags TEXT[] DEFAULT '{}',
            nodes JSONB NOT NULL,
            connections JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            author_id UUID,
            author_name VARCHAR(255),
            version VARCHAR(50) DEFAULT '1.0.0',
            requirements JSONB,
            setup_instructions TEXT,
            example_prompts TEXT[] DEFAULT '{}',
            nl_description TEXT NOT NULL,
            nl_steps TEXT[] NOT NULL,
            nl_requirements TEXT[] NOT NULL,
            is_public BOOLEAN DEFAULT FALSE,
            featured_score FLOAT DEFAULT 0.0
        )
        """)
        
        # Create index on category and tags
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_templates_category ON workflow_templates(category)
        """)
        
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_templates_is_public ON workflow_templates(is_public)
        """)
        
        # Add template_id column to workflows table if it doesn't exist
        await conn.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'workflows' AND column_name = 'template_id'
            ) THEN
                ALTER TABLE workflows ADD COLUMN template_id UUID;
            END IF;
        END $$;
        """)
        
        print("Successfully set up template tables")
        
    finally:
        await conn.close()

async def seed_sample_templates():
    """Seed sample workflow templates."""
    # Get database connection string from environment
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("DATABASE_URL environment variable not set")
        return
    
    # Connect to database
    conn = await asyncpg.connect(db_url)
    
    try:
        # Check if json_templates directory exists
        templates_dir = "json_templates"
        if not os.path.exists(templates_dir):
            print(f"Directory {templates_dir} not found")
            return
        
        # Import templates from json_templates directory
        from src.services.template_service import TemplateService
        from src.services.vector_store import VectorStoreService
        
        vector_store = VectorStoreService(conn)
        template_service = TemplateService(conn, vector_store)
        
        count = await template_service.seed_templates_from_directory(templates_dir)
        print(f"Successfully seeded {count} templates")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    # Run setup
    asyncio.run(setup_template_tables())
    
    # Seed sample templates
    asyncio.run(seed_sample_templates())