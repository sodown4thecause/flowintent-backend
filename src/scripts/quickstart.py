"""Quickstart script for the Natural Language Workflow Platform.

This script sets up the platform and runs a simple demo.
"""

import os
import sys
import asyncio
import subprocess
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.scripts.verify_env import verify_environment
from src.scripts.init_db import main as init_db
from src.scripts.seed_vector_db import main as seed_vector_db


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f" {text} ".center(80, "="))
    print("=" * 80 + "\n")


def print_step(step_num, total_steps, text):
    """Print a step in the process."""
    print(f"[{step_num}/{total_steps}] {text}...")


async def run_quickstart():
    """Run the quickstart process."""
    print_header("Natural Language Workflow Platform Quickstart")
    
    total_steps = 5
    current_step = 1
    
    # Step 1: Verify environment
    print_step(current_step, total_steps, "Verifying environment")
    env_ok, missing_vars = await verify_environment()
    
    if not env_ok:
        print("\n❌ Environment verification failed!")
        print("The following environment variables are missing:")
        for var in missing_vars:
            print(f"  - {var}")
        
        print("\nPlease set these variables in your .env file and try again.")
        return False
    
    print("✅ Environment verified successfully")
    current_step += 1
    
    # Step 2: Initialize database
    print_step(current_step, total_steps, "Initializing database")
    db_ok = await init_db()
    
    if not db_ok:
        print("\n❌ Database initialization failed!")
        print("Please check your database connection settings and try again.")
        return False
    
    print("✅ Database initialized successfully")
    current_step += 1
    
    # Step 3: Seed vector database
    print_step(current_step, total_steps, "Seeding vector database")
    seed_ok = await seed_vector_db()
    
    if not seed_ok:
        print("\n❌ Vector database seeding failed!")
        print("Please check your vector database connection settings and try again.")
        print("You can continue without sample workflows, but search functionality will be limited.")
    else:
        print("✅ Vector database seeded successfully")
    
    current_step += 1
    
    # Step 4: Start Temporal worker in background
    print_step(current_step, total_steps, "Starting Temporal worker")
    
    try:
        # Start Temporal worker in a separate process
        worker_process = subprocess.Popen(
            [sys.executable, "-m", "src.scripts.run_temporal_worker"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait a bit to ensure worker starts
        time.sleep(2)
        
        # Check if process is still running
        if worker_process.poll() is None:
            print("✅ Temporal worker started successfully")
        else:
            stdout, stderr = worker_process.communicate()
            print("\n❌ Temporal worker failed to start!")
            print(f"Error: {stderr}")
            print("You can continue without workflow execution, but some features will be limited.")
    except Exception as e:
        print(f"\n❌ Failed to start Temporal worker: {e}")
        print("You can continue without workflow execution, but some features will be limited.")
    
    current_step += 1
    
    # Step 5: Start the application
    print_step(current_step, total_steps, "Starting the application")
    
    print("\n🚀 Starting the Natural Language Workflow Platform...")
    print(f"The application will be available at: http://localhost:8000/chat")
    print("\nPress Ctrl+C to stop the application")
    
    try:
        # Start the application
        app_process = subprocess.Popen(
            [sys.executable, "-m", "src.scripts.run_ag_ui"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for the application to start
        time.sleep(2)
        
        # Check if process is still running
        if app_process.poll() is None:
            print("\n✅ Application started successfully")
            
            # Keep the script running until user interrupts
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\n👋 Stopping the application...")
                
                # Terminate processes
                app_process.terminate()
                if 'worker_process' in locals():
                    worker_process.terminate()
                
                print("✅ Application stopped")
        else:
            stdout, stderr = app_process.communicate()
            print("\n❌ Application failed to start!")
            print(f"Error: {stderr}")
            return False
    except Exception as e:
        print(f"\n❌ Failed to start application: {e}")
        return False
    
    return True


if __name__ == "__main__":
    try:
        asyncio.run(run_quickstart())
    except KeyboardInterrupt:
        print("\n\n👋 Quickstart interrupted. Exiting...")
    except Exception as e:
        print(f"\n❌ Quickstart failed: {e}")
        sys.exit(1)