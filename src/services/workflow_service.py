"""Workflow service that bridges Pydantic models with Temporal execution."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4

from ..models.workflow import (
    ExecutableWorkflow, 
    WorkflowExecution, 
    WorkflowContext,
    WorkflowStep
)
from ..services.temporal_service import temporal_service
from ..services.database import DatabaseService, get_db

logger = logging.getLogger(__name__)


class WorkflowService:
    """Service for managing workflow lifecycle and execution."""
    
    def __init__(self, db: DatabaseService):
        self.db = db
    
    async def create_workflow(
        self, 
        workflow: ExecutableWorkflow, 
        user_id: str
    ) -> ExecutableWorkflow:
        """Create and store a new workflow definition."""
        try:
            # Store workflow in database
            query = """
                INSERT INTO workflows (
                    id, name, description, steps, schedule, enabled, 
                    created_at, estimated_runtime, user_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING *
            """
            
            await self.db.execute(
                query,
                workflow.id,
                workflow.name,
                workflow.description,
                workflow.steps,  # Store as JSON
                workflow.schedule,
                workflow.enabled,
                workflow.created_at,
                workflow.estimated_runtime,
                user_id
            )
            
            logger.info(f"Created workflow {workflow.id} for user {user_id}")
            return workflow
            
        except Exception as e:
            logger.error(f"Failed to create workflow: {e}")
            raise
    
    async def get_workflow(self, workflow_id: str, user_id: str) -> Optional[ExecutableWorkflow]:
        """Get a workflow by ID."""
        try:
            query = """
                SELECT id, name, description, steps, schedule, enabled, 
                       created_at, estimated_runtime
                FROM workflows 
                WHERE id = $1 AND user_id = $2
            """
            
            row = await self.db.fetchrow(query, workflow_id, user_id)
            
            if row:
                return ExecutableWorkflow(**dict(row))
            return None
            
        except Exception as e:
            logger.error(f"Failed to get workflow {workflow_id}: {e}")
            raise
    
    async def list_workflows(
        self, 
        user_id: str, 
        limit: int = 10, 
        offset: int = 0
    ) -> List[ExecutableWorkflow]:
        """List workflows for a user."""
        try:
            query = """
                SELECT id, name, description, steps, schedule, enabled, 
                       created_at, estimated_runtime
                FROM workflows 
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """
            
            rows = await self.db.fetch(query, user_id, limit, offset)
            
            return [ExecutableWorkflow(**dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to list workflows for user {user_id}: {e}")
            raise
    
    async def execute_workflow(
        self, 
        workflow: ExecutableWorkflow, 
        user_id: str,
        context: Optional[WorkflowContext] = None
    ) -> str:
        """Execute a workflow using Temporal."""
        try:
            # Store workflow if it doesn't exist yet
            existing_workflow = await self.get_workflow(workflow.id, user_id)
            if not existing_workflow:
                await self.create_workflow(workflow, user_id)
            
            # Create execution record
            execution = WorkflowExecution(
                workflow_id=workflow.id,
                user_id=user_id,
                status="running"
            )
            
            # Store execution in database
            await self._create_execution_record(execution)
            
            # Prepare workflow parameters
            workflow_params = {
                "workflow_definition": workflow.dict(),
                "execution_id": execution.id,
                "context": context.dict() if context else {}
            }
            
            # Start Temporal workflow
            handle = await temporal_service.start_workflow(
                workflow_type="executable_workflow",
                workflow_id=execution.id,
                user_id=user_id,
                parameters=workflow_params
            )
            
            logger.info(f"Started execution {execution.id} for workflow {workflow.id}")
            return execution.id
            
        except Exception as e:
            logger.error(f"Failed to execute workflow {workflow_id}: {e}")
            # Update execution status to failed
            if 'execution' in locals():
                await self._update_execution_status(execution.id, "failed", error_details={"error": str(e)})
            raise
    
    async def get_execution(self, execution_id: str, user_id: str) -> Optional[WorkflowExecution]:
        """Get workflow execution details."""
        try:
            query = """
                SELECT id, workflow_id, user_id, status, started_at, completed_at,
                       execution_time, step_results, error_details
                FROM workflow_executions 
                WHERE id = $1 AND user_id = $2
            """
            
            row = await self.db.fetchrow(query, execution_id, user_id)
            
            if row:
                return WorkflowExecution(**dict(row))
            return None
            
        except Exception as e:
            logger.error(f"Failed to get execution {execution_id}: {e}")
            raise
    
    async def list_executions(
        self, 
        user_id: str,
        workflow_id: Optional[str] = None,
        limit: int = 10, 
        offset: int = 0
    ) -> List[WorkflowExecution]:
        """List workflow executions for a user."""
        try:
            if workflow_id:
                query = """
                    SELECT id, workflow_id, user_id, status, started_at, completed_at,
                           execution_time, step_results, error_details
                    FROM workflow_executions 
                    WHERE user_id = $1 AND workflow_id = $2
                    ORDER BY started_at DESC
                    LIMIT $3 OFFSET $4
                """
                rows = await self.db.fetch(query, user_id, workflow_id, limit, offset)
            else:
                query = """
                    SELECT id, workflow_id, user_id, status, started_at, completed_at,
                           execution_time, step_results, error_details
                    FROM workflow_executions 
                    WHERE user_id = $1
                    ORDER BY started_at DESC
                    LIMIT $2 OFFSET $3
                """
                rows = await self.db.fetch(query, user_id, limit, offset)
            
            return [WorkflowExecution(**dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to list executions for user {user_id}: {e}")
            raise
    
    async def cancel_execution(self, execution_id: str, user_id: str) -> bool:
        """Cancel a running workflow execution."""
        try:
            # Check if execution exists and belongs to user
            execution = await self.get_execution(execution_id, user_id)
            if not execution:
                raise ValueError(f"Execution {execution_id} not found")
            
            if execution.status not in ["running", "paused"]:
                raise ValueError(f"Cannot cancel execution with status {execution.status}")
            
            # Cancel Temporal workflow
            success = await temporal_service.cancel_workflow(execution_id)
            
            if success:
                # Update execution status
                await self._update_execution_status(execution_id, "cancelled")
                logger.info(f"Cancelled execution {execution_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to cancel execution {execution_id}: {e}")
            raise
    
    async def _create_execution_record(self, execution: WorkflowExecution):
        """Create execution record in database."""
        query = """
            INSERT INTO workflow_executions (
                id, workflow_id, user_id, status, started_at, 
                step_results, error_details
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        
        await self.db.execute(
            query,
            execution.id,
            execution.workflow_id,
            execution.user_id,
            execution.status,
            execution.started_at,
            execution.step_results,
            execution.error_details
        )
    
    async def _update_execution_status(
        self, 
        execution_id: str, 
        status: str,
        completed_at: Optional[datetime] = None,
        execution_time: Optional[int] = None,
        step_results: Optional[List[Dict]] = None,
        error_details: Optional[Dict] = None
    ):
        """Update execution status in database."""
        if completed_at is None and status in ["completed", "failed", "cancelled"]:
            completed_at = datetime.now()
        
        query = """
            UPDATE workflow_executions 
            SET status = $2, completed_at = $3, execution_time = $4,
                step_results = COALESCE($5, step_results),
                error_details = COALESCE($6, error_details)
            WHERE id = $1
        """
        
        await self.db.execute(
            query,
            execution_id,
            status,
            completed_at,
            execution_time,
            step_results,
            error_details
        )
    
    async def update_step_result(
        self, 
        execution_id: str, 
        step_id: str, 
        result: Dict[str, Any]
    ):
        """Update the result of a specific workflow step."""
        try:
            # Get current step results
            query = "SELECT step_results FROM workflow_executions WHERE id = $1"
            row = await self.db.fetchrow(query, execution_id)
            
            if not row:
                raise ValueError(f"Execution {execution_id} not found")
            
            step_results = row['step_results'] or []
            
            # Update or add step result
            step_found = False
            for i, step_result in enumerate(step_results):
                if step_result.get('step_id') == step_id:
                    step_results[i] = {**step_result, **result, 'step_id': step_id}
                    step_found = True
                    break
            
            if not step_found:
                step_results.append({**result, 'step_id': step_id})
            
            # Update database
            update_query = "UPDATE workflow_executions SET step_results = $2 WHERE id = $1"
            await self.db.execute(update_query, execution_id, step_results)
            
            logger.info(f"Updated step {step_id} result for execution {execution_id}")
            
        except Exception as e:
            logger.error(f"Failed to update step result: {e}")
            raise


# Dependency injection
async def get_workflow_service() -> WorkflowService:
    """Get workflow service instance."""
    db = await get_db()
    return WorkflowService(db)