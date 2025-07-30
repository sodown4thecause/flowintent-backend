"""
Monitoring service for workflow performance tracking and analysis.
"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import asyncpg
from pydantic import BaseModel

from src.config import settings
from src.models.workflow import WorkflowExecution, ExecutionMetrics


class ExecutionSummary(BaseModel):
    """Summary of workflow execution metrics."""
    workflow_id: str
    workflow_name: str
    total_executions: int
    success_rate: float
    avg_execution_time: float
    last_execution_time: Optional[datetime] = None
    error_count: int
    most_common_error: Optional[str] = None


class MonitoringService:
    """Service for monitoring workflow performance and collecting metrics."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self._alert_thresholds = {
            "execution_time": 60,  # Alert if execution takes more than 60 seconds
            "error_rate": 0.2,     # Alert if error rate exceeds 20%
            "failure_streak": 3    # Alert after 3 consecutive failures
        }
    
    async def record_execution_metrics(self, execution_id: str, metrics: ExecutionMetrics) -> None:
        """Record metrics for a workflow execution."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workflow_executions 
                SET 
                    metrics = $1,
                    updated_at = NOW()
                WHERE id = $2
                """,
                metrics.model_dump(mode='json'),
                execution_id
            )
    
    async def get_workflow_metrics(self, workflow_id: str, time_period: str = "7d") -> ExecutionSummary:
        """Get performance metrics for a specific workflow over a time period."""
        # Convert time period to timedelta
        period_map = {
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "all": timedelta(days=365*10)  # Effectively all time
        }
        period = period_map.get(time_period, period_map["7d"])
        
        async with self.db_pool.acquire() as conn:
            # Get workflow name
            workflow_name = await conn.fetchval(
                "SELECT name FROM workflows WHERE id = $1",
                workflow_id
            )
            
            # Get execution metrics
            rows = await conn.fetch(
                """
                SELECT 
                    status,
                    execution_time,
                    error_details,
                    started_at,
                    metrics
                FROM workflow_executions
                WHERE 
                    workflow_id = $1 AND
                    started_at >= NOW() - $2::interval
                ORDER BY started_at DESC
                """,
                workflow_id,
                period
            )
            
            if not rows:
                return ExecutionSummary(
                    workflow_id=workflow_id,
                    workflow_name=workflow_name or "Unknown",
                    total_executions=0,
                    success_rate=0.0,
                    avg_execution_time=0.0,
                    error_count=0,
                )
            
            # Calculate metrics
            total = len(rows)
            successful = sum(1 for row in rows if row['status'] == 'completed')
            error_count = total - successful
            success_rate = successful / total if total > 0 else 0
            
            # Calculate average execution time for successful runs
            execution_times = [row['execution_time'] for row in rows if row['execution_time'] is not None]
            avg_time = sum(execution_times) / len(execution_times) if execution_times else 0
            
            # Find most common error
            error_types = {}
            for row in rows:
                if row['error_details']:
                    error_type = self._extract_error_type(row['error_details'])
                    error_types[error_type] = error_types.get(error_type, 0) + 1
            
            most_common_error = max(error_types.items(), key=lambda x: x[1])[0] if error_types else None
            
            return ExecutionSummary(
                workflow_id=workflow_id,
                workflow_name=workflow_name or "Unknown",
                total_executions=total,
                success_rate=success_rate,
                avg_execution_time=avg_time,
                last_execution_time=rows[0]['started_at'] if rows else None,
                error_count=error_count,
                most_common_error=most_common_error
            )
    
    async def get_user_dashboard_metrics(self, user_id: str) -> Dict[str, Any]:
        """Get dashboard metrics for all user workflows."""
        async with self.db_pool.acquire() as conn:
            # Get all user workflows
            workflows = await conn.fetch(
                """
                SELECT id, name FROM workflows 
                WHERE user_id = $1 AND status != 'archived'
                """,
                user_id
            )
            
            # Get execution counts and success rates
            execution_stats = await conn.fetch(
                """
                SELECT 
                    w.id as workflow_id,
                    w.name as workflow_name,
                    COUNT(e.id) as total_executions,
                    SUM(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) as successful_executions,
                    AVG(CASE WHEN e.status = 'completed' THEN e.execution_time ELSE NULL END) as avg_execution_time,
                    MAX(e.started_at) as last_execution
                FROM workflows w
                LEFT JOIN workflow_executions e ON w.id = e.workflow_id
                WHERE 
                    w.user_id = $1 AND
                    w.status != 'archived' AND
                    (e.started_at IS NULL OR e.started_at >= NOW() - INTERVAL '30 days')
                GROUP BY w.id, w.name
                """,
                user_id
            )
            
            # Calculate overall metrics
            total_workflows = len(workflows)
            active_workflows = sum(1 for stat in execution_stats if stat['total_executions'] > 0)
            total_executions = sum(stat['total_executions'] for stat in execution_stats)
            successful_executions = sum(stat['successful_executions'] for stat in execution_stats)
            overall_success_rate = successful_executions / total_executions if total_executions > 0 else 0
            
            # Get workflows with recent errors
            workflows_with_errors = await conn.fetch(
                """
                SELECT DISTINCT w.id, w.name
                FROM workflows w
                JOIN workflow_executions e ON w.id = e.workflow_id
                WHERE 
                    w.user_id = $1 AND
                    e.status = 'failed' AND
                    e.started_at >= NOW() - INTERVAL '7 days'
                LIMIT 5
                """,
                user_id
            )
            
            return {
                "summary": {
                    "total_workflows": total_workflows,
                    "active_workflows": active_workflows,
                    "total_executions": total_executions,
                    "success_rate": overall_success_rate,
                },
                "workflow_stats": [dict(stat) for stat in execution_stats],
                "workflows_with_errors": [dict(wf) for wf in workflows_with_errors]
            }
    
    async def detect_anomalies(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Detect anomalies in workflow performance."""
        async with self.db_pool.acquire() as conn:
            # Get recent executions
            executions = await conn.fetch(
                """
                SELECT 
                    id, status, execution_time, error_details, metrics, started_at
                FROM workflow_executions
                WHERE workflow_id = $1
                ORDER BY started_at DESC
                LIMIT 20
                """,
                workflow_id
            )
            
            # Get historical averages
            historical = await conn.fetchrow(
                """
                SELECT 
                    AVG(execution_time) as avg_time,
                    STDDEV(execution_time) as std_time,
                    COUNT(*) FILTER (WHERE status = 'completed') / COUNT(*)::float as success_rate
                FROM workflow_executions
                WHERE 
                    workflow_id = $1 AND
                    started_at < (
                        SELECT started_at FROM workflow_executions
                        WHERE workflow_id = $1
                        ORDER BY started_at DESC
                        LIMIT 1 OFFSET 19
                    )
                """,
                workflow_id
            )
            
            anomalies = []
            
            if not historical or not executions:
                return anomalies
            
            # Check for execution time anomalies
            avg_time = historical['avg_time'] or 0
            std_time = historical['std_time'] or 1
            
            for execution in executions:
                if execution['execution_time'] is None:
                    continue
                    
                # Check if execution time is significantly higher than historical average
                z_score = (execution['execution_time'] - avg_time) / std_time if std_time > 0 else 0
                
                if z_score > 2:  # More than 2 standard deviations
                    anomalies.append({
                        "execution_id": execution['id'],
                        "type": "execution_time",
                        "severity": "high" if z_score > 3 else "medium",
                        "message": f"Execution time ({execution['execution_time']}s) significantly higher than average ({avg_time:.2f}s)",
                        "timestamp": execution['started_at']
                    })
            
            # Check for error rate anomalies
            recent_success_rate = sum(1 for e in executions if e['status'] == 'completed') / len(executions)
            historical_success_rate = historical['success_rate'] or 1
            
            if historical_success_rate > 0.9 and recent_success_rate < 0.7:
                anomalies.append({
                    "execution_id": None,
                    "type": "error_rate",
                    "severity": "high",
                    "message": f"Recent success rate ({recent_success_rate:.2%}) significantly lower than historical ({historical_success_rate:.2%})",
                    "timestamp": datetime.now()
                })
            
            return anomalies
    
    async def generate_optimization_suggestions(self, workflow_id: str) -> List[Dict[str, Any]]:
        """Generate suggestions for workflow optimization based on performance data."""
        async with self.db_pool.acquire() as conn:
            # Get workflow details
            workflow = await conn.fetchrow(
                """
                SELECT * FROM workflows WHERE id = $1
                """,
                workflow_id
            )
            
            if not workflow:
                return []
            
            # Get execution metrics
            executions = await conn.fetch(
                """
                SELECT 
                    id, status, execution_time, step_results, error_details, metrics
                FROM workflow_executions
                WHERE workflow_id = $1
                ORDER BY started_at DESC
                LIMIT 50
                """,
                workflow_id
            )
            
            suggestions = []
            
            if not executions:
                return suggestions
            
            # Analyze step execution times
            step_times = {}
            for execution in executions:
                if not execution['step_results']:
                    continue
                
                for step in execution['step_results']:
                    step_id = step.get('step_id')
                    if not step_id:
                        continue
                    
                    execution_time = step.get('execution_time')
                    if execution_time:
                        if step_id not in step_times:
                            step_times[step_id] = []
                        step_times[step_id].append(execution_time)
            
            # Find slow steps
            for step_id, times in step_times.items():
                avg_time = sum(times) / len(times)
                if avg_time > 5:  # More than 5 seconds on average
                    suggestions.append({
                        "type": "slow_step",
                        "step_id": step_id,
                        "message": f"Step '{step_id}' is taking {avg_time:.2f}s on average to execute",
                        "suggestion": "Consider optimizing this step or adding caching"
                    })
            
            # Analyze error patterns
            error_steps = {}
            for execution in executions:
                if execution['status'] != 'failed' or not execution['error_details']:
                    continue
                
                error_step = self._extract_error_step(execution['error_details'])
                if error_step:
                    error_steps[error_step] = error_steps.get(error_step, 0) + 1
            
            # Suggest error handling improvements
            for step_id, count in error_steps.items():
                if count >= 3:  # At least 3 errors in this step
                    suggestions.append({
                        "type": "error_prone_step",
                        "step_id": step_id,
                        "message": f"Step '{step_id}' has failed {count} times recently",
                        "suggestion": "Add more robust error handling or fallback options"
                    })
            
            return suggestions
    
    def _extract_error_type(self, error_details: Dict) -> str:
        """Extract the error type from error details."""
        if not error_details:
            return "Unknown"
        
        # Try to get error type from different possible structures
        if isinstance(error_details, dict):
            return (
                error_details.get('type') or
                error_details.get('error_type') or
                error_details.get('name', 'Unknown')
            )
        
        return "Unknown"
    
    def _extract_error_step(self, error_details: Dict) -> Optional[str]:
        """Extract the step ID where an error occurred."""
        if not error_details:
            return None
        
        if isinstance(error_details, dict):
            # Try different possible structures
            step_id = (
                error_details.get('step_id') or
                error_details.get('stepId')
            )
            
            if step_id:
                return step_id
            
            # Check if there's a nested structure with step info
            for key, value in error_details.items():
                if isinstance(value, dict) and ('step_id' in value or 'stepId' in value):
                    return value.get('step_id') or value.get('stepId')
        
        return None


class AlertService:
    """Service for generating alerts based on workflow performance."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
    
    async def check_for_alerts(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Check for workflow performance alerts."""
        async with self.db_pool.acquire() as conn:
            query = """
                SELECT 
                    w.id as workflow_id,
                    w.name as workflow_name,
                    w.user_id,
                    e.id as execution_id,
                    e.status,
                    e.execution_time,
                    e.error_details,
                    e.started_at
                FROM workflows w
                JOIN workflow_executions e ON w.id = e.workflow_id
                WHERE 
                    e.started_at >= NOW() - INTERVAL '24 hours'
                    AND w.status = 'active'
            """
            
            if user_id:
                query += " AND w.user_id = $1"
                rows = await conn.fetch(query, user_id)
            else:
                rows = await conn.fetch(query)
            
            # Group by workflow
            workflows = {}
            for row in rows:
                wf_id = row['workflow_id']
                if wf_id not in workflows:
                    workflows[wf_id] = {
                        'id': wf_id,
                        'name': row['workflow_name'],
                        'user_id': row['user_id'],
                        'executions': []
                    }
                
                workflows[wf_id]['executions'].append({
                    'id': row['execution_id'],
                    'status': row['status'],
                    'execution_time': row['execution_time'],
                    'error_details': row['error_details'],
                    'started_at': row['started_at']
                })
            
            alerts = []
            
            # Check for consecutive failures
            for wf_id, workflow in workflows.items():
                executions = sorted(workflow['executions'], key=lambda x: x['started_at'], reverse=True)
                
                # Check for consecutive failures
                failure_streak = 0
                for execution in executions:
                    if execution['status'] == 'failed':
                        failure_streak += 1
                    else:
                        break
                
                if failure_streak >= 3:
                    alerts.append({
                        'type': 'consecutive_failures',
                        'workflow_id': wf_id,
                        'workflow_name': workflow['name'],
                        'user_id': workflow['user_id'],
                        'count': failure_streak,
                        'message': f"Workflow has failed {failure_streak} times in a row",
                        'severity': 'high',
                        'timestamp': datetime.now()
                    })
                
                # Check for high error rate
                total = len(executions)
                if total >= 5:  # Only check if we have enough data
                    failures = sum(1 for e in executions if e['status'] == 'failed')
                    error_rate = failures / total
                    
                    if error_rate >= 0.5:  # 50% or higher error rate
                        alerts.append({
                            'type': 'high_error_rate',
                            'workflow_id': wf_id,
                            'workflow_name': workflow['name'],
                            'user_id': workflow['user_id'],
                            'error_rate': error_rate,
                            'message': f"Workflow has a {error_rate:.1%} error rate in the last 24 hours",
                            'severity': 'medium' if error_rate < 0.8 else 'high',
                            'timestamp': datetime.now()
                        })
                
                # Check for performance degradation
                successful = [e for e in executions if e['status'] == 'completed' and e['execution_time'] is not None]
                if len(successful) >= 5:
                    # Compare recent vs older executions
                    mid = len(successful) // 2
                    recent = successful[:mid]
                    older = successful[mid:]
                    
                    recent_avg = sum(e['execution_time'] for e in recent) / len(recent)
                    older_avg = sum(e['execution_time'] for e in older) / len(older)
                    
                    # Check if recent executions are significantly slower
                    if recent_avg > older_avg * 1.5 and recent_avg - older_avg > 5:  # 50% slower and at least 5 seconds difference
                        alerts.append({
                            'type': 'performance_degradation',
                            'workflow_id': wf_id,
                            'workflow_name': workflow['name'],
                            'user_id': workflow['user_id'],
                            'recent_avg': recent_avg,
                            'older_avg': older_avg,
                            'message': f"Workflow performance has degraded from {older_avg:.1f}s to {recent_avg:.1f}s",
                            'severity': 'medium',
                            'timestamp': datetime.now()
                        })
            
            return alerts
    
    async def save_alert(self, alert: Dict[str, Any]) -> str:
        """Save an alert to the database."""
        async with self.db_pool.acquire() as conn:
            alert_id = await conn.fetchval(
                """
                INSERT INTO workflow_alerts (
                    workflow_id, user_id, alert_type, message, severity, details
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                alert['workflow_id'],
                alert['user_id'],
                alert['type'],
                alert['message'],
                alert['severity'],
                alert
            )
            
            return alert_id
    
    async def get_user_alerts(self, user_id: str, include_resolved: bool = False) -> List[Dict[str, Any]]:
        """Get alerts for a specific user."""
        async with self.db_pool.acquire() as conn:
            query = """
                SELECT 
                    a.id, a.workflow_id, w.name as workflow_name, 
                    a.alert_type, a.message, a.severity, 
                    a.created_at, a.resolved_at, a.details
                FROM workflow_alerts a
                JOIN workflows w ON a.workflow_id = w.id
                WHERE a.user_id = $1
            """
            
            if not include_resolved:
                query += " AND a.resolved_at IS NULL"
            
            query += " ORDER BY a.created_at DESC"
            
            rows = await conn.fetch(query, user_id)
            return [dict(row) for row in rows]
    
    async def resolve_alert(self, alert_id: str, resolution_note: Optional[str] = None) -> bool:
        """Mark an alert as resolved."""
        async with self.db_pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE workflow_alerts
                SET 
                    resolved_at = NOW(),
                    resolution_note = $2
                WHERE id = $1 AND resolved_at IS NULL
                """,
                alert_id,
                resolution_note
            )
            
            return result != "UPDATE 0"


class PerformanceDashboardService:
    """Service for generating performance dashboards and reports."""
    
    def __init__(self, db_pool: asyncpg.Pool, monitoring_service: MonitoringService):
        self.db_pool = db_pool
        self.monitoring_service = monitoring_service
    
    async def generate_user_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Generate a comprehensive dashboard for a user."""
        # Get basic metrics
        metrics = await self.monitoring_service.get_user_dashboard_metrics(user_id)
        
        # Get workflow performance data
        workflow_performance = await self._get_workflow_performance(user_id)
        
        # Get recent alerts
        async with self.db_pool.acquire() as conn:
            alerts = await conn.fetch(
                """
                SELECT 
                    a.id, a.workflow_id, w.name as workflow_name, 
                    a.alert_type, a.message, a.severity, a.created_at
                FROM workflow_alerts a
                JOIN workflows w ON a.workflow_id = w.id
                WHERE 
                    a.user_id = $1 AND
                    a.resolved_at IS NULL
                ORDER BY 
                    CASE a.severity 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        ELSE 3 
                    END,
                    a.created_at DESC
                LIMIT 5
                """,
                user_id
            )
        
        # Get execution trend data
        execution_trend = await self._get_execution_trend(user_id)
        
        return {
            "summary": metrics["summary"],
            "workflow_performance": workflow_performance,
            "alerts": [dict(alert) for alert in alerts],
            "execution_trend": execution_trend,
            "workflow_stats": metrics["workflow_stats"]
        }
    
    async def generate_workflow_report(self, workflow_id: str) -> Dict[str, Any]:
        """Generate a detailed report for a specific workflow."""
        async with self.db_pool.acquire() as conn:
            # Get workflow details
            workflow = await conn.fetchrow(
                """
                SELECT * FROM workflows WHERE id = $1
                """,
                workflow_id
            )
            
            if not workflow:
                return {"error": "Workflow not found"}
            
            # Get execution statistics
            stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total_executions,
                    COUNT(*) FILTER (WHERE status = 'completed') as successful_executions,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_executions,
                    AVG(execution_time) FILTER (WHERE status = 'completed') as avg_execution_time,
                    MAX(execution_time) FILTER (WHERE status = 'completed') as max_execution_time,
                    MIN(execution_time) FILTER (WHERE status = 'completed') as min_execution_time
                FROM workflow_executions
                WHERE workflow_id = $1
                """,
                workflow_id
            )
            
            # Get recent executions
            executions = await conn.fetch(
                """
                SELECT 
                    id, status, execution_time, started_at, completed_at, 
                    error_details
                FROM workflow_executions
                WHERE workflow_id = $1
                ORDER BY started_at DESC
                LIMIT 10
                """,
                workflow_id
            )
            
            # Get execution trend
            trend = await self._get_workflow_execution_trend(workflow_id)
            
            # Get optimization suggestions
            suggestions = await self.monitoring_service.generate_optimization_suggestions(workflow_id)
            
            # Get anomalies
            anomalies = await self.monitoring_service.detect_anomalies(workflow_id)
            
            return {
                "workflow": dict(workflow),
                "statistics": dict(stats) if stats else {},
                "recent_executions": [dict(execution) for execution in executions],
                "execution_trend": trend,
                "optimization_suggestions": suggestions,
                "anomalies": anomalies
            }
    
    async def _get_workflow_performance(self, user_id: str) -> List[Dict[str, Any]]:
        """Get performance data for all user workflows."""
        async with self.db_pool.acquire() as conn:
            workflows = await conn.fetch(
                """
                SELECT id, name FROM workflows 
                WHERE user_id = $1 AND status = 'active'
                """,
                user_id
            )
            
            result = []
            for workflow in workflows:
                # Get execution statistics for the last 7 days
                stats = await conn.fetchrow(
                    """
                    SELECT 
                        COUNT(*) as executions,
                        COUNT(*) FILTER (WHERE status = 'completed') as successful,
                        AVG(execution_time) FILTER (WHERE status = 'completed') as avg_time
                    FROM workflow_executions
                    WHERE 
                        workflow_id = $1 AND
                        started_at >= NOW() - INTERVAL '7 days'
                    """,
                    workflow['id']
                )
                
                if stats and stats['executions'] > 0:
                    result.append({
                        "id": workflow['id'],
                        "name": workflow['name'],
                        "executions": stats['executions'],
                        "success_rate": stats['successful'] / stats['executions'] if stats['executions'] > 0 else 0,
                        "avg_execution_time": stats['avg_time'] or 0
                    })
            
            # Sort by number of executions (most active first)
            result.sort(key=lambda x: x['executions'], reverse=True)
            return result
    
    async def _get_execution_trend(self, user_id: str) -> Dict[str, Any]:
        """Get execution trend data for the last 30 days."""
        async with self.db_pool.acquire() as conn:
            # Get daily execution counts
            daily_counts = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('day', started_at) as day,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as successful,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed
                FROM workflow_executions e
                JOIN workflows w ON e.workflow_id = w.id
                WHERE 
                    w.user_id = $1 AND
                    started_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE_TRUNC('day', started_at)
                ORDER BY day
                """,
                user_id
            )
            
            days = []
            total_counts = []
            success_counts = []
            failure_counts = []
            
            for row in daily_counts:
                days.append(row['day'].strftime('%Y-%m-%d'))
                total_counts.append(row['total'])
                success_counts.append(row['successful'])
                failure_counts.append(row['failed'])
            
            return {
                "days": days,
                "total_executions": total_counts,
                "successful_executions": success_counts,
                "failed_executions": failure_counts
            }
    
    async def _get_workflow_execution_trend(self, workflow_id: str) -> Dict[str, Any]:
        """Get execution trend data for a specific workflow."""
        async with self.db_pool.acquire() as conn:
            # Get daily execution counts
            daily_counts = await conn.fetch(
                """
                SELECT 
                    DATE_TRUNC('day', started_at) as day,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE status = 'completed') as successful,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed,
                    AVG(execution_time) FILTER (WHERE status = 'completed') as avg_time
                FROM workflow_executions
                WHERE 
                    workflow_id = $1 AND
                    started_at >= NOW() - INTERVAL '30 days'
                GROUP BY DATE_TRUNC('day', started_at)
                ORDER BY day
                """,
                workflow_id
            )
            
            days = []
            total_counts = []
            success_counts = []
            failure_counts = []
            avg_times = []
            
            for row in daily_counts:
                days.append(row['day'].strftime('%Y-%m-%d'))
                total_counts.append(row['total'])
                success_counts.append(row['successful'])
                failure_counts.append(row['failed'])
                avg_times.append(row['avg_time'] or 0)
            
            return {
                "days": days,
                "total_executions": total_counts,
                "successful_executions": success_counts,
                "failed_executions": failure_counts,
                "avg_execution_times": avg_times
            }