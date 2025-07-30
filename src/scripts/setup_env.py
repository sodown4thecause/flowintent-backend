"""Interactive setup script for the Natural Language Workflow Platform."""

import os
import sys
import asyncio
import secrets
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f" {text} ".center(80, "="))
    print("=" * 80 + "\n")


def get_input(prompt, default=None):
    """Get user input with a default value."""
    if default:
        result = input(f"{prompt} [{default}]: ")
        return result if result else default
    else:
        return input(f"{prompt}: ")


def generate_secret_key():
    """Generate a secure random secret key."""
    return secrets.token_hex(32)


async def setup_environment():
    """Set up the environment variables."""
    print_header("Natural Language Workflow Platform Setup")
    
    print("This script will help you set up the environment variables for the platform.")
    print("Press Enter to accept the default values or enter your own.")
    
    # Check if .env file exists
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    if env_path.exists():
        overwrite = input("\n.env file already exists. Overwrite? (y/N): ").lower()
        if overwrite != "y":
            print("Setup cancelled. Existing .env file will not be modified.")
            return False
    
    # Check if .env.example exists
    if not env_example_path.exists():
        print("\n❌ .env.example file not found!")
        print("Please make sure you're running this script from the project root directory.")
        return False
    
    # Copy .env.example to .env as a starting point
    shutil.copy(env_example_path, env_path)
    print("\n✅ Created .env file from .env.example")
    
    # Load existing values from .env
    env_vars = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value
    
    # Interactive configuration
    print("\n📝 Let's configure the essential settings:\n")
    
    # OpenAI API Key
    openai_key = get_input("OpenAI API Key (required)", env_vars.get("OPENAI_API_KEY", ""))
    env_vars["OPENAI_API_KEY"] = openai_key
    
    # Cerebras API Key (optional)
    cerebras_key = get_input("Cerebras API Key (optional for faster/cheaper inference)", env_vars.get("CEREBRAS_API_KEY", ""))
    env_vars["CEREBRAS_API_KEY"] = cerebras_key
    
    # Database URL
    db_host = get_input("Database Host", env_vars.get("DATABASE_HOST", "localhost"))
    db_port = get_input("Database Port", env_vars.get("DATABASE_PORT", "5432"))
    db_name = get_input("Database Name", env_vars.get("DATABASE_NAME", "workflow_platform"))
    db_user = get_input("Database User", env_vars.get("DATABASE_USER", "postgres"))
    db_password = get_input("Database Password", env_vars.get("DATABASE_PASSWORD", "password"))
    
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    env_vars["DATABASE_URL"] = db_url
    env_vars["DATABASE_HOST"] = db_host
    env_vars["DATABASE_PORT"] = db_port
    env_vars["DATABASE_NAME"] = db_name
    env_vars["DATABASE_USER"] = db_user
    env_vars["DATABASE_PASSWORD"] = db_password
    
    # Redis URL
    redis_host = get_input("Redis Host", env_vars.get("REDIS_HOST", "localhost"))
    redis_port = get_input("Redis Port", env_vars.get("REDIS_PORT", "6379"))
    redis_db = get_input("Redis DB", env_vars.get("REDIS_DB", "0"))
    
    redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
    env_vars["REDIS_URL"] = redis_url
    env_vars["REDIS_HOST"] = redis_host
    env_vars["REDIS_PORT"] = redis_port
    env_vars["REDIS_DB"] = redis_db
    
    # Secret Key
    secret_key = get_input("Secret Key (leave empty to generate)", env_vars.get("SECRET_KEY", ""))
    if not secret_key:
        secret_key = generate_secret_key()
        print(f"Generated Secret Key: {secret_key}")
    env_vars["SECRET_KEY"] = secret_key
    
    # Temporal Host
    temporal_host = get_input("Temporal Host", env_vars.get("TEMPORAL_HOST", "localhost:7233"))
    env_vars["TEMPORAL_HOST"] = temporal_host
    
    # Environment
    environment = get_input("Environment (development/production)", env_vars.get("ENVIRONMENT", "development"))
    env_vars["ENVIRONMENT"] = environment
    
    # Debug mode
    debug = get_input("Debug Mode (true/false)", env_vars.get("DEBUG", "true" if environment == "development" else "false"))
    env_vars["DEBUG"] = debug
    
    # Write to .env file
    with open(env_path, "w") as f:
        f.write("# Natural Language Workflow Platform - Environment Variables\n\n")
        
        # OpenAI section
        f.write("# OpenAI API Configuration\n")
        f.write(f"OPENAI_API_KEY={env_vars['OPENAI_API_KEY']}\n")
        f.write(f"OPENAI_MODEL={env_vars.get('OPENAI_MODEL', 'gpt-4o')}\n")
        f.write(f"OPENAI_MODEL_MINI={env_vars.get('OPENAI_MODEL_MINI', 'gpt-4o-mini')}\n")
        f.write(f"OPENAI_EMBEDDING_MODEL={env_vars.get('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')}\n\n")
        
        # Database section
        f.write("# Database Configuration\n")
        f.write(f"DATABASE_URL={env_vars['DATABASE_URL']}\n")
        f.write(f"DATABASE_HOST={env_vars['DATABASE_HOST']}\n")
        f.write(f"DATABASE_PORT={env_vars['DATABASE_PORT']}\n")
        f.write(f"DATABASE_NAME={env_vars['DATABASE_NAME']}\n")
        f.write(f"DATABASE_USER={env_vars['DATABASE_USER']}\n")
        f.write(f"DATABASE_PASSWORD={env_vars['DATABASE_PASSWORD']}\n\n")
        
        # Redis section
        f.write("# Redis Configuration\n")
        f.write(f"REDIS_URL={env_vars['REDIS_URL']}\n")
        f.write(f"REDIS_HOST={env_vars['REDIS_HOST']}\n")
        f.write(f"REDIS_PORT={env_vars['REDIS_PORT']}\n")
        f.write(f"REDIS_DB={env_vars['REDIS_DB']}\n\n")
        
        # Application section
        f.write("# Application Configuration\n")
        f.write(f"SECRET_KEY={env_vars['SECRET_KEY']}\n")
        f.write(f"ALGORITHM={env_vars.get('ALGORITHM', 'HS256')}\n")
        f.write(f"ACCESS_TOKEN_EXPIRE_MINUTES={env_vars.get('ACCESS_TOKEN_EXPIRE_MINUTES', '30')}\n")
        f.write(f"ENVIRONMENT={env_vars['ENVIRONMENT']}\n")
        f.write(f"DEBUG={env_vars['DEBUG']}\n\n")
        
        # CORS section
        f.write("# CORS Configuration\n")
        f.write(f"ALLOWED_ORIGINS={env_vars.get('ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:8000')}\n\n")
        
        # Vector DB section
        f.write("# Vector Database Configuration\n")
        f.write(f"VECTOR_DB_URL={env_vars.get('VECTOR_DB_URL', '')}\n\n")
        
        # Temporal section
        f.write("# Temporal Configuration\n")
        f.write(f"TEMPORAL_HOST={env_vars['TEMPORAL_HOST']}\n")
        f.write(f"TEMPORAL_NAMESPACE={env_vars.get('TEMPORAL_NAMESPACE', 'default')}\n")
        f.write(f"TEMPORAL_TASK_QUEUE={env_vars.get('TEMPORAL_TASK_QUEUE', 'workflow-task-queue')}\n\n")
        
        # External API section
        f.write("# External API Configuration (Optional)\n")
        f.write(f"WEBHOOK_SECRET={env_vars.get('WEBHOOK_SECRET', '')}\n\n")
        
        # AI Services section
        f.write("# AI Services\n")
        f.write(f"GEMINI_API_KEY={env_vars.get('GEMINI_API_KEY', '')}\n")
        f.write(f"CEREBRAS_API_KEY={env_vars.get('CEREBRAS_API_KEY', '')}\n\n")
        
        # Optional integrations
        f.write("# Optional Integrations (Configure as needed)\n")
        for key in env_vars:
            if key.startswith(("GOOGLE_", "SLACK_", "TWITTER_", "YOUTUBE_", "SUPABASE_")) and key not in [
                "OPENAI_API_KEY", "DATABASE_URL", "DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME", 
                "DATABASE_USER", "DATABASE_PASSWORD", "REDIS_URL", "REDIS_HOST", "REDIS_PORT", 
                "REDIS_DB", "SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES", 
                "ENVIRONMENT", "DEBUG", "ALLOWED_ORIGINS", "VECTOR_DB_URL", "TEMPORAL_HOST", 
                "TEMPORAL_NAMESPACE", "TEMPORAL_TASK_QUEUE", "WEBHOOK_SECRET", "GEMINI_API_KEY", "CEREBRAS_API_KEY"
            ]:
                f.write(f"{key}={env_vars[key]}\n")
    
    print("\n✅ Environment configuration complete!")
    print(f"Configuration saved to: {env_path.absolute()}")
    
    print("\n🚀 Next steps:")
    print("1. Verify your environment: python -m src.scripts.verify_env")
    print("2. Initialize the database: python -m src.scripts.init_db")
    print("3. Seed the vector database: python -m src.scripts.seed_vector_db")
    print("4. Start the application: python -m src.scripts.quickstart")
    
    return True


async def main():
    """Main function."""
    try:
        success = await setup_environment()
        return success
    except KeyboardInterrupt:
        print("\n\n👋 Setup interrupted. Exiting...")
        return False
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)