"""Script to run the FastAPI application."""

import os
import sys
import uvicorn

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings


def main():
    """Run the FastAPI application."""
    print(f"🚀 Starting Natural Language Workflow Platform in {settings.environment} mode...")
    
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info"
    )


if __name__ == "__main__":
    main()