"""Main FastAPI application for the Natural Language Workflow Platform."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from pydantic_ai.ag_ui import mount_ag_ui

from src.config import settings
from src.services.database import DatabaseService, get_db
from src.services.redis_service import RedisService, get_redis
from src.services.vector_store import VectorStoreService, get_vector_store
from src.services.temporal_service import temporal_service
from src.dependencies import WorkflowDependencies, get_dependencies


# Global service instances for application lifecycle
db_service = None
redis_service = None
vector_store = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    print("🚀 Starting Natural Language Workflow Platform...")
    print(f"Environment: {settings.environment}")
    print(f"Debug mode: {settings.debug}")
    
    # Initialize global services
    global db_service, redis_service, vector_store
    
    # Initialize database service
    print("Initializing database connection...")
    db_service = await DatabaseService.create()
    
    # Initialize Redis service
    print("Initializing Redis connection...")
    redis_service = await RedisService.create()
    
    # Initialize vector store service
    print("Initializing ChromaDB vector store...")
    vector_store = VectorStoreService()
    try:
        await vector_store.initialize()
        print("ChromaDB vector store initialized successfully")
    except Exception as e:
        print(f"Warning: ChromaDB initialization failed: {e}")
        print("Vector search capabilities will be limited")
    
    # Initialize Temporal service
    print("Initializing Temporal workflow service...")
    try:
        await temporal_service.initialize()
        # Start worker in background (optional - can be run separately)
        # await temporal_service.start_worker()
        print("Temporal service initialized successfully")
    except Exception as e:
        print(f"Warning: Temporal service initialization failed: {e}")
        print("Workflows will not be available until Temporal server is running")
    
    # Initialize AI agents (will be done in a separate task)
    print("Platform services initialized successfully")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Natural Language Workflow Platform...")
    
    # Close database connection
    if db_service:
        print("Closing database connection...")
        await db_service.close()
    
    # Close Redis connection
    if redis_service:
        print("Closing Redis connection...")
        await redis_service.close()
    
    # Close vector store connection
    if vector_store:
        print("Closing vector store connection...")
        await vector_store.close()
    
    # Stop Temporal worker
    print("Stopping Temporal worker...")
    await temporal_service.stop_worker()
    
    print("All connections closed successfully")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Natural Language Workflow Platform",
        description="A conversational workflow automation platform using Pydantic AI",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan
    )
    
    # Configure CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Health check endpoint
    @app.get("/health")
    async def health_check(db: DatabaseService = Depends(get_db)):
        """Health check endpoint."""
        status = "healthy"
        db_status = "connected"
        
        # Check database connection
        try:
            await db.fetchval("SELECT 1")
        except Exception as e:
            db_status = f"error: {str(e)}"
            status = "degraded"
        
        return JSONResponse(
            content={
                "status": status,
                "environment": settings.environment,
                "version": "0.1.0",
                "services": {
                    "database": db_status
                }
            }
        )
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with basic information."""
        return JSONResponse(
            content={
                "message": "Natural Language Workflow Platform API",
                "version": "0.1.0",
                "docs": "/docs" if settings.debug else "Documentation disabled in production",
                "health": "/health"
            }
        )
    
    # Mount AG-UI application
    mount_ag_ui(
        app,
        path="/chat",
        title="Natural Language Workflow Platform",
        description="Create and manage workflows using natural language",
        system_prompt="""
        You are an AI assistant for the Natural Language Workflow Platform.
        Help users create, manage, and execute workflows using natural language.
        """
    )
    
    # Include API routers
    from src.api.router import api_router
    app.include_router(api_router)
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info"
    )