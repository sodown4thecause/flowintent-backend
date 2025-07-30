"""
AI agent for workflow optimization and improvement suggestions.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from datetime import datetime, timedelta

class WorkflowOptimization(BaseModel):
    """Optimization suggestion for a workflow."""
    optimization_id: str = Field(description="Unique optimization identifier")
    workflow_id: str = Field(description="ID of the workflow to optimize")
    optimization_type: str = Field(description="Type of optimization (performance, cost, reliability, etc.)")
    priority: str = Field(description="Priority level (high, medium, low)")
    title: str = Field(description="Short title of the optimization")
    description: str = Field(description="Detailed description of the optimization")
    expected_improvement: Dict[str, Any] = Field(description="Expected improvements (time, cost, reliability)")
    implementation_steps: List[str] = Field(description="Steps to implement the optimization")
    estimated_effort: str = Field(description="Estimated effort to implement (low, medium, high)")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the optimization suggestion")
    supporting_data: Dict[str, Any] = Field(description="Data supporting the optimization suggestion")

class WorkflowPattern(BaseModel):
    """Common workflow pattern identified through analysis."""
    pattern_id: str = Field(description="Unique pattern identifier")
    pattern_name: str = Field(description="Name of the pattern")
    description: str = Field(description="Description of the pattern")
    frequency: int = Field(description="How often this pattern occurs")
    performance_impact: str = Field(description="Impact on performance (positive, negative, neutral)")
    optimization_potential: float = Field(ge=0.0, le=1.0, description="Potential for optimization")
    example_workflows: List[str] = Field(description="Example workflow IDs that exhibit this pattern")

class OptimizationDependencies:
    """Dependencies for optimization agent."""
    def __init__(self, db_conn, monitoring_service, ml_service, ab_testing_service):
        self.db_conn = db_conn
        self.monitoring_service = monitoring_service
        self.ml_service = ml_service
        self.ab_testing_service = ab_testing_service

optimization_agent = Agent[OptimizationDependencies, List[WorkflowOptimization]](
    model='openai:gpt-4o',
    deps_type=OptimizationDependencies,
    output_type=List[WorkflowOptimization],
    system_prompt="""
    You are a workflow optimization expert. Your job is to analyze workflow performance data,
    identify patterns, and suggest specific optimizations to improve efficiency, reduce costs,
    and increase reliability.
    
    Focus on:
    1. Performance bottlenecks and slow steps
    2. Cost optimization opportunities
    3. Reliability improvements
    4. Resource utilization optimization
    5. Common anti-patterns that can be improved
    
    Provide specific, actionable recommendations with clear implementation steps.
    """
)

@optimization_agent.tool
async def get_workflow_performance_data(ctx: RunContext[OptimizationDependencies], workflow_id: str, days: int = 30) -> Dict:
    """Get performance data for a workflow over the specified period."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    performance_data = await ctx.deps.monitoring_service.get_workflow_performance(
        workflow_id=workflow_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return performance_data

@optimization_agent.tool
async def get_similar_workflows_performance(ctx: RunContext[OptimizationDependencies], workflow_id: str) -> List[Dict]:
    """Get performance data for similar workflows for comparison."""
    similar_workflows = await ctx.deps.db_conn.fetch(
        """
        SELECT w.id, w.name, w.description, 
               AVG(we.execution_time) as avg_execution_time,
               COUNT(we.id) as execution_count,
               SUM(CASE WHEN we.status = 'failed' THEN 1 ELSE 0 END) as failure_count
        FROM workflows w
        JOIN workflow_executions we ON w.id = we.workflow_id
        WHERE w.id != $1
        AND w.workflow_data::text SIMILAR TO (
            SELECT workflow_data::text FROM workflows WHERE id = $1
        )
        GROUP BY w.id, w.name, w.description
        ORDER BY execution_count DESC
        LIMIT 10
        """,
        workflow_id
    )
    
    return [dict(row) for row in similar_workflows]

@optimization_agent.tool
async def identify_common_patterns(ctx: RunContext[OptimizationDependencies], workflow_ids: List[str]) -> List[Dict]:
    """Identify common patterns across multiple workflows."""
    patterns = await ctx.deps.ml_service.identify_workflow_patterns(workflow_ids)
    return patterns

@optimization_agent.tool
async def get_cost_analysis(ctx: RunContext[OptimizationDependencies], workflow_id: str) -> Dict:
    """Get cost analysis for a workflow."""
    cost_data = await ctx.deps.monitoring_service.get_workflow_costs(workflow_id)
    return cost_data

@optimization_agent.tool
async def get_failure_analysis(ctx: RunContext[OptimizationDependencies], workflow_id: str) -> Dict:
    """Get failure analysis for a workflow."""
    failure_data = await ctx.deps.monitoring_service.get_workflow_failures(workflow_id)
    return failure_data

pattern_recognition_agent = Agent[OptimizationDependencies, List[WorkflowPattern]](
    model='openai:gpt-4o',
    deps_type=OptimizationDependencies,
    output_type=List[WorkflowPattern],
    system_prompt="""
    You are a pattern recognition expert for workflow analysis. Your job is to identify
    common patterns across workflows that can be optimized or improved.
    
    Look for:
    1. Repeated sequences of steps that could be consolidated
    2. Common integration patterns that could be optimized
    3. Error-prone patterns that need improvement
    4. Resource-intensive patterns that could be made more efficient
    5. Anti-patterns that should be avoided
    
    Provide detailed analysis of each pattern with specific examples and optimization potential.
    """
)

@pattern_recognition_agent.tool
async def analyze_workflow_structures(ctx: RunContext[OptimizationDependencies], workflow_ids: List[str]) -> List[Dict]:
    """Analyze the structure of multiple workflows to identify patterns."""
    structures = []
    
    for workflow_id in workflow_ids:
        workflow_data = await ctx.deps.db_conn.fetchrow(
            "SELECT workflow_data FROM workflows WHERE id = $1",
            workflow_id
        )
        
        if workflow_data:
            structures.append({
                "workflow_id": workflow_id,
                "structure": workflow_data["workflow_data"]
            })
    
    return structures

@pattern_recognition_agent.tool
async def get_execution_patterns(ctx: RunContext[OptimizationDependencies], workflow_ids: List[str]) -> List[Dict]:
    """Get execution patterns for multiple workflows."""
    patterns = []
    
    for workflow_id in workflow_ids:
        executions = await ctx.deps.db_conn.fetch(
            """
            SELECT step_results, execution_time, status, error_details
            FROM workflow_executions
            WHERE workflow_id = $1
            ORDER BY started_at DESC
            LIMIT 100
            """,
            workflow_id
        )
        
        patterns.append({
            "workflow_id": workflow_id,
            "executions": [dict(row) for row in executions]
        })
    
    return patterns

class OptimizationAgentService:
    """Service for AI-powered workflow optimization."""
    
    def __init__(self, db_pool, monitoring_service, ml_service, ab_testing_service):
        """Initialize the optimization agent service."""
        self.db_pool = db_pool
        self.monitoring_service = monitoring_service
        self.ml_service = ml_service
        self.ab_testing_service = ab_testing_service
        
    async def analyze_workflow_optimization(self, workflow_id: str) -> List[WorkflowOptimization]:
        """Analyze a workflow and provide optimization suggestions."""
        async with self.db_pool.acquire() as conn:
            deps = OptimizationDependencies(
                conn, 
                self.monitoring_service, 
                self.ml_service,
                self.ab_testing_service
            )
            
            result = await optimization_agent.run(
                f"Analyze workflow {workflow_id} for optimization opportunities",
                deps=deps
            )
            
            return result.output
    
    async def identify_workflow_patterns(self, workflow_ids: List[str]) -> List[WorkflowPattern]:
        """Identify common patterns across multiple workflows."""
        async with self.db_pool.acquire() as conn:
            deps = OptimizationDependencies(
                conn, 
                self.monitoring_service, 
                self.ml_service,
                self.ab_testing_service
            )
            
            result = await pattern_recognition_agent.run(
                f"Identify patterns in workflows: {', '.join(workflow_ids)}",
                deps=deps
            )
            
            return result.output
    
    async def apply_optimization(self, workflow_id: str, optimization: WorkflowOptimization) -> Dict[str, Any]:
        """Apply an optimization to a workflow."""
        async with self.db_pool.acquire() as conn:
            # Create A/B test for the optimization
            test_id = await self.ab_testing_service.create_test(
                name=f"Optimization: {optimization.title}",
                description=optimization.description,
                workflow_id=workflow_id,
                optimization_data=optimization.dict()
            )
            
            # Record the optimization application
            await conn.execute(
                """
                INSERT INTO workflow_optimizations (
                    id, workflow_id, optimization_type, title, description,
                    expected_improvement, implementation_steps, status,
                    ab_test_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                optimization.optimization_id,
                workflow_id,
                optimization.optimization_type,
                optimization.title,
                optimization.description,
                optimization.expected_improvement,
                optimization.implementation_steps,
                "testing",
                test_id,
                datetime.now()
            )
            
            return {
                "optimization_id": optimization.optimization_id,
                "ab_test_id": test_id,
                "status": "testing",
                "message": f"Optimization '{optimization.title}' is now being tested"
            }
    
    async def get_optimization_results(self, optimization_id: str) -> Dict[str, Any]:
        """Get the results of an applied optimization."""
        async with self.db_pool.acquire() as conn:
            optimization_data = await conn.fetchrow(
                """
                SELECT * FROM workflow_optimizations WHERE id = $1
                """,
                optimization_id
            )
            
            if not optimization_data:
                return {"error": "Optimization not found"}
            
            # Get A/B test results
            ab_test_results = await self.ab_testing_service.get_test_results(
                optimization_data["ab_test_id"]
            )
            
            return {
                "optimization": dict(optimization_data),
                "ab_test_results": ab_test_results,
                "recommendation": self._generate_recommendation(ab_test_results)
            }
    
    def _generate_recommendation(self, ab_test_results: Dict[str, Any]) -> str:
        """Generate a recommendation based on A/B test results."""
        if not ab_test_results or "statistical_significance" not in ab_test_results:
            return "Insufficient data for recommendation"
        
        if ab_test_results["statistical_significance"] < 0.95:
            return "Results are not statistically significant. Continue testing."
        
        improvement = ab_test_results.get("improvement_percentage", 0)
        
        if improvement > 10:
            return "Strong positive results. Recommend implementing the optimization."
        elif improvement > 5:
            return "Moderate positive results. Consider implementing the optimization."
        elif improvement > -5:
            return "Neutral results. Optimization may not be worth implementing."
        else:
            return "Negative results. Do not implement this optimization."