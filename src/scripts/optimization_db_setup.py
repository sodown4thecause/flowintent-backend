"""
Script to set up database tables for workflow optimization.
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def setup_optimization_tables():
    """Set up database tables for workflow optimization."""
    # Get database connection string from environment
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("DATABASE_URL environment variable not set")
        return
    
    # Connect to database
    conn = await asyncpg.connect(db_url)
    
    try:
        # Create workflow_optimizations table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_optimizations (
            optimization_id VARCHAR(255) PRIMARY KEY,
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            optimization_type VARCHAR(100) NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            impact_score FLOAT NOT NULL CHECK (impact_score >= 0 AND impact_score <= 1),
            effort_score FLOAT NOT NULL CHECK (effort_score >= 0 AND effort_score <= 1),
            priority VARCHAR(50) NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
            estimated_improvement JSONB NOT NULL,
            implementation_steps TEXT[] NOT NULL,
            risks TEXT[] DEFAULT '{}',
            confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            applied BOOLEAN DEFAULT FALSE,
            applied_by UUID REFERENCES users(id),
            applied_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """)
        
        # Create workflow_optimization_results table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_optimization_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            optimization_id VARCHAR(255) NOT NULL REFERENCES workflow_optimizations(optimization_id) ON DELETE CASCADE,
            actual_improvement JSONB NOT NULL,
            success BOOLEAN NOT NULL,
            measured_at TIMESTAMP DEFAULT NOW(),
            measurement_period_days INTEGER DEFAULT 7,
            notes TEXT
        )
        """)
        
        # Create workflow_performance_metrics table
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_performance_metrics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            metric_name VARCHAR(100) NOT NULL,
            metric_value FLOAT NOT NULL,
            metric_unit VARCHAR(50),
            measured_at TIMESTAMP DEFAULT NOW(),
            measurement_context JSONB
        )
        """)
        
        # Create workflow_ab_tests table for optimization validation
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_ab_tests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
            test_name VARCHAR(255) NOT NULL,
            control_version JSONB NOT NULL,
            test_version JSONB NOT NULL,
            traffic_split FLOAT DEFAULT 0.5 CHECK (traffic_split >= 0 AND traffic_split <= 1),
            status VARCHAR(50) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'stopped')),
            start_date TIMESTAMP DEFAULT NOW(),
            end_date TIMESTAMP,
            results JSONB,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        
        # Create indexes for performance
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_optimizations_workflow_id ON workflow_optimizations(workflow_id)
        """)
        
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_optimizations_applied ON workflow_optimizations(applied)
        """)
        
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_performance_metrics_workflow_id ON workflow_performance_metrics(workflow_id)
        """)
        
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_performance_metrics_measured_at ON workflow_performance_metrics(measured_at)
        """)
        
        await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ab_tests_workflow_id ON workflow_ab_tests(workflow_id)
        """)
        
        print("Successfully set up optimization tables")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    # Run setup
    asyncio.run(setup_optimization_tables())