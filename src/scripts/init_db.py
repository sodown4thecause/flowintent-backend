"""Script to initialize the database schema."""

import os
import sys
import asyncio
import asyncpg

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings


async def create_tables(conn):
    """Create database tables."""
    await conn.execute("""
    -- Users and authentication
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email VARCHAR(255) UNIQUE NOT NULL,
        name VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255),
        preferences JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        last_login TIMESTAMP,
        subscription_tier VARCHAR(50) DEFAULT 'free',
        is_active BOOLEAN DEFAULT TRUE,
        is_verified BOOLEAN DEFAULT FALSE
    );

    -- Workflow storage
    CREATE TABLE IF NOT EXISTS workflows (
        id VARCHAR(255) PRIMARY KEY,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        steps JSONB NOT NULL,
        schedule VARCHAR(100),
        enabled BOOLEAN DEFAULT TRUE,
        created_at VARCHAR(100) NOT NULL,
        estimated_runtime INTEGER DEFAULT 60,
        execution_count INTEGER DEFAULT 0,
        last_execution TIMESTAMP,
        is_template BOOLEAN DEFAULT FALSE,
        tags TEXT[] DEFAULT '{}'
    );

    -- Integration management
    CREATE TABLE IF NOT EXISTS user_integrations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        service_name VARCHAR(100) NOT NULL,
        auth_data JSONB NOT NULL, -- encrypted
        configuration JSONB DEFAULT '{}',
        status VARCHAR(50) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT NOW(),
        last_used TIMESTAMP,
        UNIQUE(user_id, service_name)
    );

    -- Execution tracking
    CREATE TABLE IF NOT EXISTS workflow_executions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        workflow_id VARCHAR(255) REFERENCES workflows(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        status VARCHAR(50) DEFAULT 'running',
        started_at TIMESTAMP DEFAULT NOW(),
        completed_at TIMESTAMP,
        execution_time INTEGER, -- seconds
        step_results JSONB DEFAULT '[]',
        error_details JSONB
    );
    
    -- Workflow templates
    CREATE TABLE IF NOT EXISTS workflow_templates (
        id VARCHAR(255) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        template JSONB NOT NULL,
        category VARCHAR(100),
        tags TEXT[] DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        usage_count INTEGER DEFAULT 0,
        rating FLOAT DEFAULT 0,
        is_public BOOLEAN DEFAULT FALSE
    );
    
    -- Vector embeddings for semantic search
    CREATE TABLE IF NOT EXISTS vector_embeddings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        object_id VARCHAR(255) NOT NULL,
        object_type VARCHAR(50) NOT NULL,
        embedding FLOAT[] NOT NULL,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(object_id, object_type)
    );
    
    -- Workflow intents
    CREATE TABLE IF NOT EXISTS workflow_intents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        goal TEXT NOT NULL,
        input_data JSONB DEFAULT '{}',
        expected_output TEXT,
        constraints JSONB DEFAULT '[]',
        integrations TEXT[] DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW(),
        workflow_id VARCHAR(255) REFERENCES workflows(id) ON DELETE SET NULL
    );
    
    -- Conversation history
    CREATE TABLE IF NOT EXISTS conversations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        conversation_id VARCHAR(255) NOT NULL,
        message JSONB NOT NULL,
        timestamp TIMESTAMP DEFAULT NOW(),
        workflow_id VARCHAR(255) REFERENCES workflows(id) ON DELETE SET NULL,
        intent_id UUID REFERENCES workflow_intents(id) ON DELETE SET NULL
    );
    
    -- Template ratings
    CREATE TABLE IF NOT EXISTS template_ratings (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        template_id VARCHAR(255) REFERENCES workflow_templates(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
        review TEXT,
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(template_id, user_id)
    );
    
    -- Template usage tracking
    CREATE TABLE IF NOT EXISTS template_usage (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        template_id VARCHAR(255) REFERENCES workflow_templates(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        workflow_id VARCHAR(255) REFERENCES workflows(id) ON DELETE SET NULL,
        used_at TIMESTAMP DEFAULT NOW(),
        customizations JSONB DEFAULT '{}'
    );
    
    -- Template comments
    CREATE TABLE IF NOT EXISTS template_comments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        template_id VARCHAR(255) REFERENCES workflow_templates(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        parent_id UUID REFERENCES template_comments(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP
    );
    
    -- Template collections
    CREATE TABLE IF NOT EXISTS template_collections (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255) NOT NULL,
        description TEXT NOT NULL,
        created_by UUID REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        template_ids TEXT[] DEFAULT '{}',
        visibility VARCHAR(50) DEFAULT 'private',
        tags TEXT[] DEFAULT '{}'
    );

    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_workflows_user_id ON workflows(user_id);
    CREATE INDEX IF NOT EXISTS idx_workflows_status ON workflows(enabled);
    CREATE INDEX IF NOT EXISTS idx_workflows_template ON workflows(is_template);
    CREATE INDEX IF NOT EXISTS idx_executions_workflow_id ON workflow_executions(workflow_id);
    CREATE INDEX IF NOT EXISTS idx_executions_status ON workflow_executions(status);
    CREATE INDEX IF NOT EXISTS idx_integrations_user_service ON user_integrations(user_id, service_name);
    CREATE INDEX IF NOT EXISTS idx_templates_category ON workflow_templates(category);
    CREATE INDEX IF NOT EXISTS idx_templates_public ON workflow_templates(is_public);
    CREATE INDEX IF NOT EXISTS idx_vector_object ON vector_embeddings(object_id, object_type);
    CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
    CREATE INDEX IF NOT EXISTS idx_conversations_conversation ON conversations(conversation_id);
    CREATE INDEX IF NOT EXISTS idx_intents_user ON workflow_intents(user_id);
    """)


async def main():
    """Initialize the database schema."""
    print(f"🔧 Initializing database schema for {settings.database_name}...")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(settings.database_url)
        
        # Create extension for UUID generation if it doesn't exist
        try:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
            print("✅ Created pgcrypto extension")
        except Exception as e:
            print(f"❌ Error creating pgcrypto extension: {e}")
        
        # Create tables
        await create_tables(conn)
        print("✅ Created database tables")
        
        # Close connection
        await conn.close()
        
        print("✅ Database initialization complete!")
        return True
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)