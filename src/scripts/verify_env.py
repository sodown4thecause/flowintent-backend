"""Script to verify the environment for the Natural Language Workflow Platform."""

import os
import sys
import asyncio
import httpx
import asyncpg
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings


async def check_database_connection():
    """Check if the database connection is working."""
    print("Checking database connection...")
    
    try:
        # Try to connect to the database
        conn = await asyncpg.connect(settings.database_url)
        
        # Execute a simple query
        await conn.execute("SELECT 1")
        
        # Close connection
        await conn.close()
        
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


async def check_openai_api():
    """Check if the OpenAI API key is valid."""
    print("Checking OpenAI API key...")
    
    if not settings.openai_api_key:
        print("❌ OpenAI API key not set")
        return False
    
    try:
        # Try to make a simple API call
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"}
            )
        
        if response.status_code == 200:
            print("✅ OpenAI API key is valid")
            return True
        else:
            print(f"❌ OpenAI API key is invalid: {response.text}")
            return False
    except Exception as e:
        print(f"❌ OpenAI API check failed: {e}")
        return False


async def check_temporal_connection():
    """Check if the Temporal server is reachable."""
    print("Checking Temporal server connection...")
    
    try:
        # Try to connect to the Temporal server
        # This is a simple check that just verifies the host is reachable
        host, port = settings.temporal_host.split(":")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"http://{host}:{port}/health", timeout=5.0)
        
        if response.status_code == 200:
            print("✅ Temporal server is reachable")
            return True
        else:
            print(f"❌ Temporal server returned status code {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Temporal server connection failed: {e}")
        print("Note: This is not critical if you're not using workflow execution features")
        return False


async def check_required_env_vars():
    """Check if all required environment variables are set."""
    print("Checking required environment variables...")
    
    required_vars = [
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "SECRET_KEY"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        return False, missing_vars
    
    print("✅ All required environment variables are set")
    return True, []


async def verify_environment():
    """Verify the environment for the Natural Language Workflow Platform."""
    print("\n🔍 Verifying environment for Natural Language Workflow Platform...\n")
    
    # Check required environment variables
    env_vars_ok, missing_vars = await check_required_env_vars()
    
    if not env_vars_ok:
        return False, missing_vars
    
    # Check database connection
    db_ok = await check_database_connection()
    
    # Check OpenAI API
    openai_ok = await check_openai_api()
    
    # Check Temporal connection (optional)
    temporal_ok = await check_temporal_connection()
    
    # Overall status
    all_ok = env_vars_ok and db_ok and openai_ok
    
    if all_ok:
        print("\n✅ Environment verification successful!")
        if not temporal_ok:
            print("⚠️  Warning: Temporal server is not reachable. Workflow execution will not work.")
    else:
        print("\n❌ Environment verification failed!")
    
    return all_ok, missing_vars


async def main():
    """Main function."""
    all_ok, missing_vars = await verify_environment()
    return all_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)