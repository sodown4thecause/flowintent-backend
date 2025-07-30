#!/usr/bin/env python3
"""
Temporal Worker Script

This script runs a dedicated Temporal worker that processes workflows.
Run this separately from your main FastAPI application for better scalability.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.temporal_service import temporal_service
from config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TemporalWorkerRunner:
    """Manages the Temporal worker lifecycle."""
    
    def __init__(self):
        self.running = False
        self.shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the Temporal worker."""
        logger.info("Starting Temporal worker...")
        logger.info(f"Temporal Host: {settings.temporal_host}")
        logger.info(f"Temporal Namespace: {settings.temporal_namespace}")
        logger.info(f"Task Queue: {settings.temporal_task_queue}")
        
        try:
            # Initialize and start the worker
            await temporal_service.initialize()
            await temporal_service.start_worker()
            
            self.running = True
            logger.info("✅ Temporal worker started successfully")
            logger.info("Worker is ready to process workflows...")
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"❌ Failed to start Temporal worker: {e}")
            raise
    
    async def stop(self):
        """Stop the Temporal worker."""
        if self.running:
            logger.info("Stopping Temporal worker...")
            await temporal_service.stop_worker()
            self.running = False
            self.shutdown_event.set()
            logger.info("✅ Temporal worker stopped")
    
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.stop())


async def main():
    """Main function to run the Temporal worker."""
    worker_runner = TemporalWorkerRunner()
    
    # Set up signal handlers for graceful shutdown
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, worker_runner.handle_shutdown)
    
    try:
        await worker_runner.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
    finally:
        await worker_runner.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker shutdown complete")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)