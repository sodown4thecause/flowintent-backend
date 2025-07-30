"""
Machine learning service for workflow performance prediction.
"""
import json
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import mean_absolute_error, r2_score
import joblib
import os

class WorkflowFeatureExtractor:
    """Extract features from workflow data for ML models."""
    
    def __init__(self):
        self.label_encoders = {}
        self.scaler = StandardScaler()
        
    def extract_features(self, workflow_data: Dict[str, Any]) -> Dict[str, float]:
        """Extract numerical features from workflow data."""
        features = {}
        
        # Basic workflow structure features
        nodes = workflow_data.get("nodes", [])
        connections = workflow_data.get("connections", {})
        
        features["node_count"] = len(nodes)
        features["connection_count"] = sum(len(conns) for conns in connections.values())
        features["avg_connections_per_node"] = features["connection_count"] / max(1, features["node_count"])
        
        # Node type distribution
        node_types = {}
        for node in nodes:
            node_type = node.get("type", "unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1
        
        # Common node type features
        features["trigger_nodes"] = sum(1 for nt in node_types if "trigger" in nt.lower())
        features["action_nodes"] = sum(1 for nt in node_types if "action" in nt.lower())
        features["condition_nodes"] = sum(1 for nt in node_types if "condition" in nt.lower() or "if" in nt.lower())
        features["transform_nodes"] = sum(1 for nt in node_types if "transform" in nt.lower() or "set" in nt.lower())
        features["api_nodes"] = sum(1 for nt in node_types if "http" in nt.lower() or "api" in nt.lower())
        features["ai_nodes"] = sum(1 for nt in node_types if "ai" in nt.lower() or "openai" in nt.lower() or "gpt" in nt.lower())
        
        # Complexity indicators
        features["max_node_parameters"] = max(len(node.get("parameters", {})) for node in nodes) if nodes else 0
        features["total_parameters"] = sum(len(node.get("parameters", {})) for node in nodes)
        features["has_loops"] = 1 if self._detect_loops(connections) else 0
        features["max_depth"] = self._calculate_max_depth(connections)
        features["parallel_branches"] = self._count_parallel_branches(connections)
        
        # Integration complexity
        integrations = set()
        for node in nodes:
            node_type = node.get("type", "")
            if "." in node_type:
                integration = node_type.split(".")[0]
                integrations.add(integration)
        
        features["unique_integrations"] = len(integrations)
        features["has_external_apis"] = 1 if any("http" in i.lower() for i in integrations) else 0
        features["has_databases"] = 1 if any(db in str(integrations).lower() for db in ["postgres", "mysql", "mongo"]) else 0
        
        return features
    
    def _detect_loops(self, connections: Dict[str, Any]) -> bool:
        """Detect if there are loops in the workflow graph."""
        # Simple cycle detection using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            
            for connection_type in connections.get(node, {}):
                for connection in connections[node][connection_type]:
                    next_node = connection.get("node")
                    if next_node and has_cycle(next_node):
                        return True
            
            rec_stack.remove(node)
            return False
        
        for node in connections:
            if has_cycle(node):
                return True
        
        return False
    
    def _calculate_max_depth(self, connections: Dict[str, Any]) -> int:
        """Calculate the maximum depth of the workflow graph."""
        def dfs_depth(node, visited):
            if node in visited:
                return 0
            
            visited.add(node)
            max_child_depth = 0
            
            for connection_type in connections.get(node, {}):
                for connection in connections[node][connection_type]:
                    next_node = connection.get("node")
                    if next_node:
                        child_depth = dfs_depth(next_node, visited.copy())
                        max_child_depth = max(max_child_depth, child_depth)
            
            return max_child_depth + 1
        
        max_depth = 0
        for node in connections:
            depth = dfs_depth(node, set())
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    def _count_parallel_branches(self, connections: Dict[str, Any]) -> int:
        """Count the number of parallel branches in the workflow."""
        max_parallel = 0
        
        for node in connections:
            total_outgoing = 0
            for connection_type in connections[node]:
                total_outgoing += len(connections[node][connection_type])
            max_parallel = max(max_parallel, total_outgoing)
        
        return max_parallel

class MLPredictionService:
    """Machine learning service for workflow performance prediction."""
    
    def __init__(self, db_pool):
        """Initialize the ML prediction service."""
        self.db_pool = db_pool
        self.feature_extractor = WorkflowFeatureExtractor()
        self.models = {}
        self.model_path = "models/workflow_prediction"
        
        # Ensure model directory exists
        os.makedirs(self.model_path, exist_ok=True)
    
    async def train_performance_model(self, retrain: bool = False) -> Dict[str, Any]:
        """Train ML models to predict workflow performance."""
        if not retrain and self._models_exist():
            self._load_models()
            return {"status": "loaded_existing", "message": "Loaded existing trained models"}
        
        # Collect training data
        training_data = await self._collect_training_data()
        
        if len(training_data) < 50:
            return {"status": "insufficient_data", "message": f"Need at least 50 samples, got {len(training_data)}"}
        
        # Prepare features and targets
        X, y_time, y_success = self._prepare_training_data(training_data)
        
        # Train execution time prediction model
        time_model = GradientBoostingRegressor(n_estimators=100, random_state=42)
        X_train, X_test, y_time_train, y_time_test = train_test_split(X, y_time, test_size=0.2, random_state=42)
        
        time_model.fit(X_train, y_time_train)
        time_predictions = time_model.predict(X_test)
        time_mae = mean_absolute_error(y_time_test, time_predictions)
        time_r2 = r2_score(y_time_test, time_predictions)
        
        # Train success rate prediction model
        success_model = RandomForestRegressor(n_estimators=100, random_state=42)
        X_train, X_test, y_success_train, y_success_test = train_test_split(X, y_success, test_size=0.2, random_state=42)
        
        success_model.fit(X_train, y_success_train)
        success_predictions = success_model.predict(X_test)
        success_mae = mean_absolute_error(y_success_test, success_predictions)
        success_r2 = r2_score(y_success_test, success_predictions)
        
        # Store models
        self.models = {
            "execution_time": time_model,
            "success_rate": success_model
        }
        
        # Save models to disk
        self._save_models()
        
        return {
            "status": "trained",
            "message": "Successfully trained performance prediction models",
            "metrics": {
                "execution_time": {"mae": time_mae, "r2": time_r2},
                "success_rate": {"mae": success_mae, "r2": success_r2}
            },
            "training_samples": len(training_data)
        }
    
    async def predict_performance(self, workflow_data: Dict[str, Any]) -> Dict[str, float]:
        """Predict workflow performance metrics."""
        if not self.models:
            if self._models_exist():
                self._load_models()
            else:
                raise ValueError("No trained models available. Please train models first.")
        
        # Extract features
        features = self.feature_extractor.extract_features(workflow_data)
        feature_vector = np.array([list(features.values())]).reshape(1, -1)
        
        # Make predictions
        predictions = {}
        
        if "execution_time" in self.models:
            predicted_time = self.models["execution_time"].predict(feature_vector)[0]
            predictions["predicted_execution_time"] = max(1.0, predicted_time)  # Minimum 1 second
        
        if "success_rate" in self.models:
            predicted_success = self.models["success_rate"].predict(feature_vector)[0]
            predictions["predicted_success_rate"] = max(0.0, min(1.0, predicted_success))  # Clamp to [0,1]
        
        # Calculate derived metrics
        if "predicted_execution_time" in predictions and "predicted_success_rate" in predictions:
            predictions["predicted_cost"] = self._estimate_cost(
                predictions["predicted_execution_time"],
                features.get("ai_nodes", 0),
                features.get("api_nodes", 0)
            )
            
            predictions["reliability_score"] = self._calculate_reliability_score(
                predictions["predicted_success_rate"],
                features.get("has_loops", 0),
                features.get("unique_integrations", 0)
            )
        
        return predictions
    
    async def get_optimization_suggestions(self, workflow_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get ML-based optimization suggestions."""
        current_predictions = await self.predict_performance(workflow_data)
        features = self.feature_extractor.extract_features(workflow_data)
        
        suggestions = []
        
        # Analyze bottlenecks and suggest optimizations
        if features.get("ai_nodes", 0) > 3:
            suggestions.append({
                "type": "reduce_ai_calls",
                "title": "Reduce AI API Calls",
                "description": "Consider batching AI operations or caching results to reduce API calls",
                "estimated_time_savings": current_predictions.get("predicted_execution_time", 0) * 0.2,
                "confidence": 0.8
            })
        
        if features.get("api_nodes", 0) > 5:
            suggestions.append({
                "type": "parallel_api_calls",
                "title": "Parallelize API Calls",
                "description": "Execute independent API calls in parallel to reduce total execution time",
                "estimated_time_savings": current_predictions.get("predicted_execution_time", 0) * 0.3,
                "confidence": 0.7
            })
        
        if features.get("has_loops", 0) and current_predictions.get("predicted_success_rate", 1.0) < 0.9:
            suggestions.append({
                "type": "add_error_handling",
                "title": "Improve Error Handling in Loops",
                "description": "Add better error handling and retry logic in loop structures",
                "estimated_reliability_improvement": 0.1,
                "confidence": 0.9
            })
        
        if features.get("unique_integrations", 0) > 3:
            suggestions.append({
                "type": "consolidate_integrations",
                "title": "Consolidate Integrations",
                "description": "Consider using fewer, more comprehensive integrations to reduce complexity",
                "estimated_reliability_improvement": 0.05,
                "confidence": 0.6
            })
        
        return suggestions
    
    async def _collect_training_data(self) -> List[Dict[str, Any]]:
        """Collect historical workflow execution data for training."""
        async with self.db_pool.acquire() as conn:
            # Get workflow executions with performance data
            rows = await conn.fetch(
                """
                SELECT 
                    w.workflow_data,
                    we.execution_time,
                    we.status,
                    COUNT(*) OVER (PARTITION BY w.id) as execution_count
                FROM workflows w
                JOIN workflow_executions we ON w.id = we.workflow_id
                WHERE we.execution_time IS NOT NULL 
                AND we.started_at >= NOW() - INTERVAL '90 days'
                AND execution_count >= 5  -- Only workflows with sufficient execution history
                """
            )
            
            training_data = []
            for row in rows:
                workflow_data = json.loads(row["workflow_data"])
                execution_time = float(row["execution_time"])
                success = 1.0 if row["status"] == "completed" else 0.0
                
                training_data.append({
                    "workflow_data": workflow_data,
                    "execution_time": execution_time,
                    "success": success
                })
            
            return training_data
    
    def _prepare_training_data(self, training_data: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Prepare training data for ML models."""
        features_list = []
        execution_times = []
        success_rates = []
        
        for data in training_data:
            features = self.feature_extractor.extract_features(data["workflow_data"])
            features_list.append(list(features.values()))
            execution_times.append(data["execution_time"])
            success_rates.append(data["success"])
        
        X = np.array(features_list)
        y_time = np.array(execution_times)
        y_success = np.array(success_rates)
        
        # Scale features
        X = self.feature_extractor.scaler.fit_transform(X)
        
        return X, y_time, y_success
    
    def _estimate_cost(self, execution_time: float, ai_nodes: int, api_nodes: int) -> float:
        """Estimate workflow execution cost."""
        base_cost = execution_time * 0.001  # $0.001 per second
        ai_cost = ai_nodes * 0.02  # $0.02 per AI call
        api_cost = api_nodes * 0.005  # $0.005 per API call
        
        return base_cost + ai_cost + api_cost
    
    def _calculate_reliability_score(self, success_rate: float, has_loops: int, integrations: int) -> float:
        """Calculate a reliability score based on various factors."""
        base_score = success_rate
        
        # Penalize complexity
        complexity_penalty = (has_loops * 0.05) + (integrations * 0.02)
        
        return max(0.0, min(1.0, base_score - complexity_penalty))
    
    def _models_exist(self) -> bool:
        """Check if trained models exist on disk."""
        return (os.path.exists(f"{self.model_path}/execution_time_model.joblib") and
                os.path.exists(f"{self.model_path}/success_rate_model.joblib"))
    
    def _save_models(self):
        """Save trained models to disk."""
        if "execution_time" in self.models:
            joblib.dump(self.models["execution_time"], f"{self.model_path}/execution_time_model.joblib")
        
        if "success_rate" in self.models:
            joblib.dump(self.models["success_rate"], f"{self.model_path}/success_rate_model.joblib")
        
        # Save feature extractor
        joblib.dump(self.feature_extractor, f"{self.model_path}/feature_extractor.joblib")
    
    def _load_models(self):
        """Load trained models from disk."""
        try:
            self.models["execution_time"] = joblib.load(f"{self.model_path}/execution_time_model.joblib")
            self.models["success_rate"] = joblib.load(f"{self.model_path}/success_rate_model.joblib")
            self.feature_extractor = joblib.load(f"{self.model_path}/feature_extractor.joblib")
        except Exception as e:
            print(f"Error loading models: {e}")
            self.models = {}