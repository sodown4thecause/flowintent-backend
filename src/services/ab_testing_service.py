"""
A/B testing service for validating workflow optimizations.
"""
import json
import random
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import asyncpg

class ABTest(BaseModel):
    """A/B test configuration."""
    id: str = Field(description="Test ID")
    workflow_id: str = Field(description="Workflow being tested")
    test_name: str = Field(description="Name of the test")
    control_version: Dict[str, Any] = Field(description="Control version configuration")
    test_version: Dict[str, Any] = Field(description="Test version configuration")
    traffic_split: float = Field(default=0.5, description="Percentage of traffic to test version")
    status: str = Field(default="running", description="Test status")
    start_date: datetime = Field(description="Test start date")
    end_date: Optional[datetime] = Field(default=None, description="Test end date")
    results: Optional[Dict[str, Any]] = Field(default=None, description="Test results")

class ABTestResult(BaseModel):
    """Results of an A/B test."""
    test_id: str = Field(description="Test ID")
    control_metrics: Dict[str, float] = Field(description="Control version metrics")
    test_metrics: Dict[str, float] = Field(description="Test version metrics")
    statistical_significance: bool = Field(description="Whether results are statistically significant")
    confidence_level: float = Field(description="Confidence level of the results")
    recommendation: str = Field(description="Recommendation based on results")
    sample_size: Dict[str, int] = Field(description="Sample sizes for each version")

class ABTestingService:
    """Service for managing A/B tests for workflow optimizations."""
    
    def __init__(self, db_pool):
        """Initialize the A/B testing service."""
        self.db_pool = db_pool
        
    async def create_ab_test(
        self, 
        workflow_id: str, 
        test_name: str,
        control_version: Dict[str, Any],
        test_version: Dict[str, Any],
        traffic_split: float = 0.5,
        duration_days: int = 7,
        created_by: str = None
    ) -> str:
        """Create a new A/B test."""
        async with self.db_pool.acquire() as conn:
            test_id = await conn.fetchval(
                """
                INSERT INTO workflow_ab_tests (
                    workflow_id, test_name, control_version, test_version,
                    traffic_split, end_date, created_by
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                workflow_id,
                test_name,
                json.dumps(control_version),
                json.dumps(test_version),
                traffic_split,
                datetime.now() + timedelta(days=duration_days),
                created_by
            )
            
            return str(test_id)
    
    async def get_test_version(self, workflow_id: str, execution_id: str) -> Dict[str, Any]:
        """Determine which version to use for a workflow execution."""
        async with self.db_pool.acquire() as conn:
            # Get active test for this workflow
            test = await conn.fetchrow(
                """
                SELECT * FROM workflow_ab_tests 
                WHERE workflow_id = $1 AND status = 'running'
                AND (end_date IS NULL OR end_date > NOW())
                ORDER BY start_date DESC
                LIMIT 1
                """,
                workflow_id
            )
            
            if not test:
                # No active test, return None (use default version)
                return None
            
            # Determine version based on traffic split
            use_test_version = random.random() < test["traffic_split"]
            
            # Log the assignment
            await conn.execute(
                """
                INSERT INTO ab_test_assignments (
                    test_id, execution_id, version_assigned, assigned_at
                ) VALUES ($1, $2, $3, NOW())
                ON CONFLICT (test_id, execution_id) DO NOTHING
                """,
                test["id"],
                execution_id,
                "test" if use_test_version else "control"
            )
            
            if use_test_version:
                return json.loads(test["test_version"])
            else:
                return json.loads(test["control_version"])
    
    async def record_test_metric(
        self, 
        test_id: str, 
        execution_id: str, 
        metric_name: str, 
        metric_value: float
    ):
        """Record a metric for an A/B test execution."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ab_test_metrics (
                    test_id, execution_id, metric_name, metric_value, recorded_at
                ) VALUES ($1, $2, $3, $4, NOW())
                """,
                test_id, execution_id, metric_name, metric_value
            )
    
    async def analyze_test_results(self, test_id: str) -> ABTestResult:
        """Analyze the results of an A/B test."""
        async with self.db_pool.acquire() as conn:
            # Get test details
            test = await conn.fetchrow(
                """
                SELECT * FROM workflow_ab_tests WHERE id = $1
                """,
                test_id
            )
            
            if not test:
                raise ValueError(f"Test {test_id} not found")
            
            # Get metrics for both versions
            metrics = await conn.fetch(
                """
                SELECT 
                    ata.version_assigned,
                    atm.metric_name,
                    AVG(atm.metric_value) as avg_value,
                    COUNT(*) as sample_size,
                    STDDEV(atm.metric_value) as std_dev
                FROM ab_test_assignments ata
                JOIN ab_test_metrics atm ON ata.test_id = atm.test_id AND ata.execution_id = atm.execution_id
                WHERE ata.test_id = $1
                GROUP BY ata.version_assigned, atm.metric_name
                """,
                test_id
            )
            
            # Organize metrics by version
            control_metrics = {}
            test_metrics = {}
            sample_sizes = {"control": 0, "test": 0}
            
            for metric in metrics:
                version = metric["version_assigned"]
                metric_name = metric["metric_name"]
                avg_value = float(metric["avg_value"])
                
                if version == "control":
                    control_metrics[metric_name] = avg_value
                    sample_sizes["control"] = max(sample_sizes["control"], metric["sample_size"])
                else:
                    test_metrics[metric_name] = avg_value
                    sample_sizes["test"] = max(sample_sizes["test"], metric["sample_size"])
            
            # Perform statistical analysis
            statistical_significance = self._calculate_statistical_significance(
                control_metrics, test_metrics, sample_sizes
            )
            
            # Generate recommendation
            recommendation = self._generate_recommendation(
                control_metrics, test_metrics, statistical_significance
            )
            
            result = ABTestResult(
                test_id=test_id,
                control_metrics=control_metrics,
                test_metrics=test_metrics,
                statistical_significance=statistical_significance["significant"],
                confidence_level=statistical_significance["confidence"],
                recommendation=recommendation,
                sample_size=sample_sizes
            )
            
            # Store results
            await conn.execute(
                """
                UPDATE workflow_ab_tests 
                SET results = $1, status = 'completed'
                WHERE id = $2
                """,
                json.dumps(result.dict()),
                test_id
            )
            
            return result
    
    async def stop_test(self, test_id: str) -> bool:
        """Stop an active A/B test."""
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE workflow_ab_tests 
                SET status = 'stopped', end_date = NOW()
                WHERE id = $1 AND status = 'running'
                """,
                test_id
            )
            
            return result != "UPDATE 0"
    
    async def get_active_tests(self, workflow_id: Optional[str] = None) -> List[ABTest]:
        """Get active A/B tests."""
        async with self.db_pool.acquire() as conn:
            query = """
            SELECT * FROM workflow_ab_tests 
            WHERE status = 'running' AND (end_date IS NULL OR end_date > NOW())
            """
            params = []
            
            if workflow_id:
                query += " AND workflow_id = $1"
                params.append(workflow_id)
            
            query += " ORDER BY start_date DESC"
            
            rows = await conn.fetch(query, *params)
            
            tests = []
            for row in rows:
                test = ABTest(
                    id=str(row["id"]),
                    workflow_id=str(row["workflow_id"]),
                    test_name=row["test_name"],
                    control_version=json.loads(row["control_version"]),
                    test_version=json.loads(row["test_version"]),
                    traffic_split=row["traffic_split"],
                    status=row["status"],
                    start_date=row["start_date"],
                    end_date=row["end_date"],
                    results=json.loads(row["results"]) if row["results"] else None
                )
                tests.append(test)
            
            return tests
    
    def _calculate_statistical_significance(
        self, 
        control_metrics: Dict[str, float], 
        test_metrics: Dict[str, float], 
        sample_sizes: Dict[str, int]
    ) -> Dict[str, Any]:
        """Calculate statistical significance of test results."""
        # Simplified statistical analysis
        # In production, you'd use proper statistical tests like t-test or chi-square
        
        min_sample_size = 100  # Minimum sample size for significance
        confidence_threshold = 0.95
        
        if sample_sizes["control"] < min_sample_size or sample_sizes["test"] < min_sample_size:
            return {
                "significant": False,
                "confidence": 0.0,
                "reason": "Insufficient sample size"
            }
        
        # Check for meaningful differences in key metrics
        significant_differences = 0
        total_metrics = 0
        
        for metric_name in control_metrics:
            if metric_name in test_metrics:
                control_value = control_metrics[metric_name]
                test_value = test_metrics[metric_name]
                
                if control_value > 0:  # Avoid division by zero
                    relative_change = abs(test_value - control_value) / control_value
                    if relative_change > 0.05:  # 5% threshold for meaningful change
                        significant_differences += 1
                
                total_metrics += 1
        
        if total_metrics == 0:
            return {
                "significant": False,
                "confidence": 0.0,
                "reason": "No comparable metrics"
            }
        
        # Simple confidence calculation based on sample size and effect size
        confidence = min(0.99, (significant_differences / total_metrics) * 
                        (min(sample_sizes["control"], sample_sizes["test"]) / min_sample_size))
        
        return {
            "significant": confidence >= confidence_threshold,
            "confidence": confidence,
            "reason": f"Based on {significant_differences}/{total_metrics} metrics showing significant change"
        }
    
    def _generate_recommendation(
        self, 
        control_metrics: Dict[str, float], 
        test_metrics: Dict[str, float], 
        statistical_significance: Dict[str, Any]
    ) -> str:
        """Generate a recommendation based on test results."""
        if not statistical_significance["significant"]:
            return f"No significant difference found. {statistical_significance['reason']}. Continue with control version."
        
        # Compare key metrics
        improvements = 0
        degradations = 0
        
        key_metrics = ["execution_time", "success_rate", "cost_per_execution"]
        
        for metric in key_metrics:
            if metric in control_metrics and metric in test_metrics:
                control_value = control_metrics[metric]
                test_value = test_metrics[metric]
                
                if metric == "execution_time" or metric == "cost_per_execution":
                    # Lower is better
                    if test_value < control_value:
                        improvements += 1
                    elif test_value > control_value:
                        degradations += 1
                else:
                    # Higher is better (success_rate, etc.)
                    if test_value > control_value:
                        improvements += 1
                    elif test_value < control_value:
                        degradations += 1
        
        if improvements > degradations:
            return "Test version shows significant improvements. Recommend deploying test version."
        elif degradations > improvements:
            return "Test version shows degradations. Recommend keeping control version."
        else:
            return "Mixed results. Consider running test longer or with larger sample size."
    
    async def setup_ab_test_tables(self):
        """Set up database tables for A/B testing."""
        async with self.db_pool.acquire() as conn:
            # Create ab_test_assignments table
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_assignments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                test_id UUID NOT NULL REFERENCES workflow_ab_tests(id) ON DELETE CASCADE,
                execution_id VARCHAR(255) NOT NULL,
                version_assigned VARCHAR(50) NOT NULL CHECK (version_assigned IN ('control', 'test')),
                assigned_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(test_id, execution_id)
            )
            """)
            
            # Create ab_test_metrics table
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS ab_test_metrics (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                test_id UUID NOT NULL REFERENCES workflow_ab_tests(id) ON DELETE CASCADE,
                execution_id VARCHAR(255) NOT NULL,
                metric_name VARCHAR(100) NOT NULL,
                metric_value FLOAT NOT NULL,
                recorded_at TIMESTAMP DEFAULT NOW()
            )
            """)
            
            # Create indexes
            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ab_assignments_test_id ON ab_test_assignments(test_id)
            """)
            
            await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ab_metrics_test_id ON ab_test_metrics(test_id)
            """)