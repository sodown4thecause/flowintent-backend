"""Temporal workflow service for managing workflow execution."""

import asyncio
import logging
from typing import Any, Dict, Optional
from temporalio.client import Client, WorkflowHandle
from temporalio.worker import Worker
from temporalio.common import RetryPolicy
from datetime import timedelta

from ..workflows.base import BaseWorkflow, WorkflowInput, log_activity
from ..workflows.natural_language import (
    NaturalLanguageWorkflow,
    process_natural_language,
    store_workflow_result
)
from ..workflows.executable_workflow import (
    ExecutableWorkflowRunner,
    execute_trigger_step,
    execute_action_step,
    execute_condition_step,
    execute_transform_step,
    update_execution_progress
)
from ..config import settings


logger = logging.getLogger(__name__)


class TemporalService:
    """Service for managing Temporal workflows."""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self.worker: Optional[Worker] = None
        self._worker_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Initialize Temporal client and worker."""
        try:
            # Connect to Temporal server
            self.client = await Client.connect(
                target_host=getattr(settings, 'TEMPORAL_HOST', 'localhost:7233'),
                namespace=getattr(settings, 'TEMPORAL_NAMESPACE', 'default')
            )
            
            # Create worker
            self.worker = Worker(
                self.client,
                task_queue="workflow-task-queue",
                workflows=[
                    BaseWorkflow, 
                    NaturalLanguageWorkflow, 
                    ExecutableWorkflowRunner
                ],
                activities=[
                    log_activity,
                    process_natural_language,
                    store_workflow_result,
                    execute_trigger_step,
                    execute_action_step,
                    execute_condition_step,
                    execute_transform_step,
                    update_execution_progress
                ],
            )
            
            logger.info("Temporal service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Temporal service: {str(e)}")
            raise
    
    async def start_worker(self):
        """Start the Temporal worker."""
        if not self.worker:
            await self.initialize()
        
        try:
            logger.info("Starting Temporal worker...")
            self._worker_task = asyncio.create_task(self.worker.run())
            logger.info("Temporal worker started")
        except Exception as e:
            logger.error(f"Failed to start Temporal worker: {str(e)}")
            raise
    
    async def stop_worker(self):
        """Stop the Temporal worker."""
        if self._worker_task:
            logger.info("Stopping Temporal worker...")
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("Temporal worker stopped")
    
    async def start_workflow(
        self,
        workflow_type: str,
        workflow_id: str,
        user_id: str,
        parameters: Dict[str, Any]
    ) -> WorkflowHandle:
        """Start a new workflow."""
        if not self.client:
            await self.initialize()
        
        # Map workflow type to workflow class
        workflow_class = self._get_workflow_class(workflow_type)
        
        input_data = WorkflowInput(
            workflow_id=workflow_id,
            user_id=user_id,
            parameters=parameters
        )
        
        try:
            handle = await self.client.start_workflow(
                workflow_class.run,
                input_data,
                id=workflow_id,
                task_queue="workflow-task-queue",
                execution_timeout=timedelta(hours=1),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            
            logger.info(f"Started workflow {workflow_id} of type {workflow_type}")
            return handle
            
        except Exception as e:
            logger.error(f"Failed to start workflow {workflow_id}: {str(e)}")
            raise
    
    async def get_workflow_result(self, workflow_id: str) -> Any:
        """Get the result of a completed workflow."""
        if not self.client:
            await self.initialize()
        
        try:
            handle = self.client.get_workflow_handle(workflow_id)
            result = await handle.result()
            return result
        except Exception as e:
            logger.error(f"Failed to get workflow result for {workflow_id}: {str(e)}")
            raise
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow."""
        if not self.client:
            await self.initialize()
        
        try:
            handle = self.client.get_workflow_handle(workflow_id)
            await handle.cancel()
            logger.info(f"Cancelled workflow {workflow_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel workflow {workflow_id}: {str(e)}")
            return False
    
    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """Get the status of a workflow."""
        if not self.client:
            await self.initialize()
        
        try:
            handle = self.client.get_workflow_handle(workflow_id)
            description = await handle.describe()
            
            return {
                "workflow_id": workflow_id,
                "status": description.status.name,
                "start_time": description.start_time.isoformat() if description.start_time else None,
                "close_time": description.close_time.isoformat() if description.close_time else None,
                "execution_time": description.execution_time,
                "run_id": description.run_id,
            }
        except Exception as e:
            logger.error(f"Failed to get workflow status for {workflow_id}: {str(e)}")
            raise
    
    def _get_workflow_class(self, workflow_type: str):
        """Map workflow type string to workflow class."""
        workflow_map = {
            "base": BaseWorkflow,
            "natural_language": NaturalLanguageWorkflow,
            "executable_workflow": ExecutableWorkflowRunner,
        }
        
        if workflow_type not in workflow_map:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        
        return workflow_map[workflow_type]


# Global instance
temporal_service = TemporalService()