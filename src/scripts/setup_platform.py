#!/usr/bin/env python3
"""
Setup script for the Natural Language Workflow Platform.
This script:
1. Initializes the database schema
2. Seeds the vector database with workflow templates
3. Creates a default admin user
"""

import os
import sys
import asyncio
import getpass
import argparse
from typing import Dict, Any, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.scripts.init_db import main as init_db
from src.scripts.seed_vector_db import main as seed_vector_db
from src.services.database import DatabaseService
from src.config import settings


async def create_admin_user(email: str, name: str, password: str) -> bool:
    """Create an admin user in the database."""
    print(f"👤 Creating admin user: {email}")
    
    try:
        # Connect to database
        db = DatabaseService()
        await db.connect(settings.database_url)
        
        # Check if user already exists
        user = await db.fetchrow("SELECT * FROM users WHERE email = $1", email)
        if user:
            print(f"⚠️ User {email} already exists")
            await db.close()
            return False
        
        # Create user
        query = """
            INSERT INTO users (email, name, password_hash, is_admin, subscription_tier)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """
        
        # In a real application, you would hash the password
        # For this demo, we're using a simple hash function
        import hashlib
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        user_id = await db.fetchval(
            query, email, name, password_hash, True, "premium"
        )
        
        await db.close()
        
        if user_id:
            print(f"✅ Created admin user: {email}")
            return True
        else:
            print(f"❌ Failed to create admin user")
            return False
            
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        return False


async def setup_platform(create_user: bool = True):
    """Set up the entire platform."""
    print("=" * 80)
    print("🚀 Setting up Natural Language Workflow Platform")
    print("=" * 80)
    
    # Step 1: Initialize database
    print("\n📦 Step 1: Initializing database schema")
    db_success = await init_db()
    
    if not db_success:
        print("❌ Database initialization failed. Aborting setup.")
        return False
    
    # Step 2: Seed vector database
    print("\n🧠 Step 2: Seeding vector database with workflow templates")
    vector_success = await seed_vector_db()
    
    if not vector_success:
        print("⚠️ Vector database seeding failed. Continuing with setup.")
    
    # Step 3: Create admin user (optional)
    if create_user:
        print("\n👤 Step 3: Creating admin user")
        
        email = input("Enter admin email: ")
        name = input("Enter admin name: ")
        password = getpass.getpass("Enter admin password: ")
        
        user_success = await create_admin_user(email, name, password)
        
        if not user_success:
            print("⚠️ Admin user creation failed. Continuing with setup.")
    
    print("\n✅ Platform setup completed!")
    print("\nNext steps:")
    print("1. Start the application: uv run python src/scripts/run_app.py")
    print("2. Start the Temporal worker: uv run python src/scripts/run_temporal_worker.py")
    print("3. Access the API at: http://localhost:8000")
    print("4. Access the documentation at: http://localhost:8000/docs")
    
    return True


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Set up the Natural Language Workflow Platform")
    parser.add_argument("--no-user", action="store_true", help="Skip admin user creation")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    success = asyncio.run(setup_platform(not args.no_user))
    sys.exit(0 if success else 1)