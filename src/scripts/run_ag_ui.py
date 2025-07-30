"""Script to run the AG-UI interface for the Natural Language Workflow Platform."""

import os
import sys
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_ai.ag_ui import mount_ag_ui

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.config import settings
from src.agents.platform_agent import create_platform_agent_app


def create_app():
    """Create the FastAPI application with AG-UI mounted."""
    app = FastAPI(
        title="Natural Language Workflow Platform",
        description="Create and manage workflows using natural language",
        version="0.1.0"
    )
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Mount AG-UI
    ag_ui_app = create_platform_agent_app()
    app.mount("/chat", ag_ui_app)
    
    @app.get("/")
    async def root():
        """Root endpoint that redirects to the chat interface."""
        return {
            "message": "Natural Language Workflow Platform",
            "chat_url": "/chat",
            "docs_url": "/docs" if settings.debug else None
        }
    
    return app


def main():
    """Run the AG-UI application."""
    app = create_app()
    
    print(f"🚀 Starting AG-UI interface on http://localhost:8000/chat")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )


if __name__ == "__main__":
    main()