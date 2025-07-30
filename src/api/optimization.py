"""
API endpoints for workflow optimization.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.dependencies import get_db_pool, get_vector_store_service
from src.services.monitoring_service import MonitoringService
from src.agents.optimization_agent import OptimizationService, WorkflowOptimization, WorkflowAnalysis

router = APIRouter(prefix="/optimization", tags=["optimization"])

async def get_monitoring_service(
    db_pool=Depends(get_db_pool)
):
    """Get monitoring service dependency."""
    return MonitoringService(db_pool)

async def get_optimization_service(
    db_pool=Depends(get_db_pool),
    vector_store_service=Depends(get_vector_store_service),
    monitoring_service=Depends(get_monitoring_service)
):
    """Get optimization service dependency."""
    return OptimizationService(db_pool, vector_store_service, monitoring_service)

class OptimizationRequest(BaseModel):
    """Request model for workflow optimization."""
    workflow_id: str = Field(description="ID of the workflow to optimize")
    optimization_types: Optional[List[str]] = Field(
        default=None, 
        description="Specific types of optimizations to focus on"
    )

class OptimizationApplicationRequest(BaseModel):
    """Request model for applying an optimization."""
    optimization_id: str = Field(description="ID of the optimization to apply")
    user_id: str = Field(description="ID of the user applying the optimization")

class OptimizationResponse(BaseModel):
    """Response model for optimization operations."""
    success: bool = Field(description="Whether the operation was successful")
    message: str = Field(description="Response message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Additional response data")

@router.get("/analyze/{workflow_id}", response_model=WorkflowAnalysis)
async def analyze_workflow(
    workflow_id: str,
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Analyze a workflow's performance and identify optimization opportunities."""
    try:
        analysis = await optimization_service.analyze_workflow(workflow_id)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze workflow: {str(e)}")

@router.post("/generate", response_model=List[WorkflowOptimization])
async def generate_optimizations(
    request: OptimizationRequest,
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Generate AI-powered optimization suggestions for a workflow."""
    try:
        optimizations = await optimization_service.generate_optimizations(request.workflow_id)
        return optimizations
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate optimizations: {str(e)}")

@router.get("/workflow/{workflow_id}", response_model=List[WorkflowOptimization])
async def get_workflow_optimizations(
    workflow_id: str,
    applied: Optional[bool] = Query(None, description="Filter by applied status"),
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Get optimization suggestions for a specific workflow."""
    try:
        async with optimization_service.db_pool.acquire() as conn:
            query = """
            SELECT 
                optimization_id, workflow_id, optimization_type, title, description,
                impact_score, effort_score, priority, estimated_improvement,
                implementation_steps, risks, confidence, applied, created_at
            FROM workflow_optimizations 
            WHERE workflow_id = $1
            """
            params = [workflow_id]
            
            if applied is not None:
                query += " AND applied = $2"
                params.append(applied)
            
            query += " ORDER BY impact_score DESC, created_at DESC"
            
            rows = await conn.fetch(query, *params)
            
            optimizations = []
            for row in rows:
                opt = WorkflowOptimization(
                    optimization_id=row["optimization_id"],
                    workflow_id=row["workflow_id"],
                    optimization_type=row["optimization_type"],
                    title=row["title"],
                    description=row["description"],
                    impact_score=row["impact_score"],
                    effort_score=row["effort_score"],
                    priority=row["priority"],
                    estimated_improvement=row["estimated_improvement"],
                    implementation_steps=row["implementation_steps"],
                    risks=row["risks"],
                    confidence=row["confidence"]
                )
                optimizations.append(opt)
            
            return optimizations
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get optimizations: {str(e)}")

@router.post("/apply", response_model=OptimizationResponse)
async def apply_optimization(
    request: OptimizationApplicationRequest,
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Apply an optimization to a workflow."""
    try:
        result = await optimization_service.apply_optimization(
            request.optimization_id, 
            request.user_id
        )
        
        return OptimizationResponse(
            success=True,
            message=result["message"],
            data=result
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply optimization: {str(e)}")

@router.get("/results/{optimization_id}", response_model=Dict[str, Any])
async def get_optimization_results(
    optimization_id: str,
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Get the results of an applied optimization."""
    try:
        results = await optimization_service.get_optimization_results(optimization_id)
        return results
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get optimization results: {str(e)}")

@router.get("/patterns", response_model=List[Dict[str, Any]])
async def get_optimization_patterns(
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Get common optimization patterns and their effectiveness."""
    try:
        async with optimization_service.db_pool.acquire() as conn:
            patterns = await conn.fetch(
                """
                SELECT 
                    optimization_type,
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN applied = true THEN 1 END) as applied_count,
                    AVG(impact_score) as avg_impact_score,
                    AVG(confidence) as avg_confidence,
                    AVG(CASE WHEN applied = true THEN impact_score END) as avg_applied_impact
                FROM workflow_optimizations 
                GROUP BY optimization_type
                ORDER BY avg_impact_score DESC
                """
            )
            
            return [dict(row) for row in patterns]
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get optimization patterns: {str(e)}")

@router.get("/dashboard/{workflow_id}", response_model=Dict[str, Any])
async def get_optimization_dashboard(
    workflow_id: str,
    optimization_service: OptimizationService = Depends(get_optimization_service)
):
    """Get optimization dashboard data for a workflow."""
    try:
        async with optimization_service.db_pool.acquire() as conn:
            # Get optimization summary
            summary = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_optimizations,
                    COUNT(CASE WHEN applied = true THEN 1 END) as applied_optimizations,
                    AVG(impact_score) as avg_impact_score,
                    SUM(CASE WHEN applied = true THEN impact_score ELSE 0 END) as total_applied_impact
                FROM workflow_optimizations 
                WHERE workflow_id = $1
                """,
                workflow_id
            )
            
            # Get recent optimizations
            recent_optimizations = await conn.fetch(
                """
                SELECT optimization_id, title, optimization_type, impact_score, applied, created_at
                FROM workflow_optimizations 
                WHERE workflow_id = $1
                ORDER BY created_at DESC
                LIMIT 5
                """,
                workflow_id
            )
            
            # Get performance trends
            performance_trends = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('day', measured_at) as date,
                    metric_name,
                    AVG(metric_value) as avg_value
                FROM workflow_performance_metrics 
                WHERE workflow_id = $1 AND measured_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE_TRUNC('day', measured_at), metric_name
                ORDER BY date DESC
                """,
                workflow_id
            )
            
            return {
                "summary": dict(summary) if summary else {},
                "recent_optimizations": [dict(row) for row in recent_optimizations],
                "performance_trends": [dict(row) for row in performance_trends]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get optimization dashboard: {str(e)}")