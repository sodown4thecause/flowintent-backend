"""Community service for workflow sharing and templates."""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json

from src.models.community import (
    WorkflowTemplate,
    TemplateRating,
    TemplateUsage,
    TemplateComment,
    TemplateCollection,
    TemplateSearchQuery,
    TemplateSearchResult,
    TemplateAdaptationRequest,
    TemplateAdaptationResult,
    CommunityStats,
    ModerationRequest,
    TemplateVisibility,
    TemplateCategory,
    TemplateStatus
)
from src.models.workflow import ExecutableWorkflow, WorkflowStep
from src.services.database import DatabaseService
from src.services.vector_store import VectorStoreService
from src.errors import ValidationError, DatabaseError, handle_errors

logger = logging.getLogger(__name__)


class CommunityService:
    """Service for managing workflow templates and community features."""
    
    def __init__(self, db: DatabaseService, vector_store: VectorStoreService):
        self.db = db
        self.vector_store = vector_store
    
    # Template Management
    
    @handle_errors
    async def create_template(
        self,
        template: WorkflowTemplate,
        user_id: str
    ) -> WorkflowTemplate:
        """Create a new workflow template."""
        template.created_by = user_id
        template.created_at = datetime.now()
        template.updated_at = datetime.now()
        
        # Store in database
        query = """
            INSERT INTO workflow_templates (
                id, name, description, template, category, tags, created_by,
                created_at, updated_at, visibility, status, usage_count,
                rating, rating_count, required_integrations, estimated_runtime,
                complexity_level
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            RETURNING *
        """
        
        await self.db.execute(
            query,
            template.id,
            template.name,
            template.description,
            json.dumps(template.template_data),
            template.category.value,
            template.tags,
            template.created_by,
            template.created_at,
            template.updated_at,
            template.visibility.value,
            template.status.value,
            template.usage_count,
            template.rating,
            template.rating_count,
            template.required_integrations,
            template.estimated_runtime,
            template.complexity_level
        )
        
        # Store in vector database for search
        if template.visibility == TemplateVisibility.PUBLIC:
            await self._index_template_for_search(template)
        
        logger.info(f"Created template {template.id} by user {user_id}")
        return template
    
    @handle_errors
    async def get_template(self, template_id: str, user_id: Optional[str] = None) -> Optional[WorkflowTemplate]:
        """Get a workflow template by ID."""
        query = """
            SELECT * FROM workflow_templates 
            WHERE id = $1 AND (visibility = 'public' OR created_by = $2)
        """
        
        row = await self.db.fetchrow(query, template_id, user_id)
        if not row:
            return None
        
        return self._row_to_template(row)
    
    @handle_errors
    async def update_template(
        self,
        template_id: str,
        updates: Dict[str, Any],
        user_id: str
    ) -> Optional[WorkflowTemplate]:
        """Update a workflow template."""
        # Check ownership
        existing = await self.get_template(template_id, user_id)
        if not existing or existing.created_by != user_id:
            raise ValidationError("Template not found or access denied")
        
        # Build update query
        set_clauses = []
        values = []
        param_count = 1
        
        for field, value in updates.items():
            if field in ['name', 'description', 'category', 'tags', 'visibility', 'status', 'complexity_level']:
                set_clauses.append(f"{field} = ${param_count}")
                values.append(value.value if hasattr(value, 'value') else value)
                param_count += 1
        
        if not set_clauses:
            return existing
        
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now())
        param_count += 1
        
        values.extend([template_id, user_id])
        
        query = f"""
            UPDATE workflow_templates 
            SET {', '.join(set_clauses)}
            WHERE id = ${param_count} AND created_by = ${param_count + 1}
            RETURNING *
        """
        
        row = await self.db.fetchrow(query, *values)
        if not row:
            return None
        
        template = self._row_to_template(row)
        
        # Update vector index if public
        if template.visibility == TemplateVisibility.PUBLIC:
            await self._index_template_for_search(template)
        
        return template
    
    @handle_errors
    async def delete_template(self, template_id: str, user_id: str) -> bool:
        """Delete a workflow template."""
        # Check ownership
        existing = await self.get_template(template_id, user_id)
        if not existing or existing.created_by != user_id:
            return False
        
        # Delete from database
        query = "DELETE FROM workflow_templates WHERE id = $1 AND created_by = $2"
        result = await self.db.execute(query, template_id, user_id)
        
        # Remove from vector index
        await self.vector_store.delete(template_id, "workflows")
        
        logger.info(f"Deleted template {template_id} by user {user_id}")
        return "DELETE 1" in result
    
    # Template Search and Discovery
    
    @handle_errors
    async def search_templates(self, search_query: TemplateSearchQuery) -> TemplateSearchResult:
        """Search for workflow templates."""
        # Build SQL query
        where_clauses = ["visibility = 'public'", "status = 'published'"]
        params = []
        param_count = 1
        
        # Text search
        if search_query.query:
            # Use vector search for semantic matching
            vector_results = await self.vector_store.search(
                query=search_query.query,
                collection_type="workflows",
                limit=search_query.limit * 2,  # Get more results for filtering
                threshold=0.6
            )
            
            if vector_results:
                template_ids = [result.content.get("id") for result in vector_results]
                placeholders = ",".join([f"${i}" for i in range(param_count, param_count + len(template_ids))])
                where_clauses.append(f"id IN ({placeholders})")
                params.extend(template_ids)
                param_count += len(template_ids)
        
        # Category filter
        if search_query.category:
            where_clauses.append(f"category = ${param_count}")
            params.append(search_query.category.value)
            param_count += 1
        
        # Tags filter
        if search_query.tags:
            where_clauses.append(f"tags && ${param_count}")
            params.append(search_query.tags)
            param_count += 1
        
        # Required integrations filter
        if search_query.required_integrations:
            where_clauses.append(f"required_integrations && ${param_count}")
            params.append(search_query.required_integrations)
            param_count += 1
        
        # Complexity level filter
        if search_query.complexity_level:
            where_clauses.append(f"complexity_level = ${param_count}")
            params.append(search_query.complexity_level)
            param_count += 1
        
        # Rating filter
        if search_query.min_rating:
            where_clauses.append(f"rating >= ${param_count}")
            params.append(search_query.min_rating)
            param_count += 1
        
        # Creator filter
        if search_query.created_by:
            where_clauses.append(f"created_by = ${param_count}")
            params.append(search_query.created_by)
            param_count += 1
        
        # Build ORDER BY clause
        order_by = f"ORDER BY {search_query.sort_by} {search_query.sort_order.upper()}"
        
        # Count query
        count_query = f"""
            SELECT COUNT(*) FROM workflow_templates 
            WHERE {' AND '.join(where_clauses)}
        """
        
        total_count = await self.db.fetchval(count_query, *params)
        
        # Main query with pagination
        main_query = f"""
            SELECT * FROM workflow_templates 
            WHERE {' AND '.join(where_clauses)}
            {order_by}
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        params.extend([search_query.limit, search_query.offset])
        
        rows = await self.db.fetch(main_query, *params)
        templates = [self._row_to_template(row) for row in rows]
        
        # Generate facets
        facets = await self._generate_search_facets(search_query)
        
        return TemplateSearchResult(
            templates=templates,
            total_count=total_count,
            has_more=search_query.offset + len(templates) < total_count,
            facets=facets
        )
    
    @handle_errors
    async def get_popular_templates(self, limit: int = 10) -> List[WorkflowTemplate]:
        """Get popular workflow templates."""
        query = """
            SELECT * FROM workflow_templates 
            WHERE visibility = 'public' AND status = 'published'
            ORDER BY usage_count DESC, rating DESC
            LIMIT $1
        """
        
        rows = await self.db.fetch(query, limit)
        return [self._row_to_template(row) for row in rows]
    
    @handle_errors
    async def get_recent_templates(self, limit: int = 10) -> List[WorkflowTemplate]:
        """Get recently published templates."""
        query = """
            SELECT * FROM workflow_templates 
            WHERE visibility = 'public' AND status = 'published'
            ORDER BY created_at DESC
            LIMIT $1
        """
        
        rows = await self.db.fetch(query, limit)
        return [self._row_to_template(row) for row in rows]
    
    # Template Usage and Adaptation
    
    @handle_errors
    async def use_template(
        self,
        template_id: str,
        user_id: str,
        customizations: Dict[str, Any] = None
    ) -> TemplateAdaptationResult:
        """Use a template to create a new workflow."""
        template = await self.get_template(template_id)
        if not template:
            raise ValidationError("Template not found")
        
        try:
            # Create workflow from template
            workflow_data = template.template_data.copy()
            
            # Apply customizations
            if customizations:
                workflow_data.update(customizations)
            
            # Create ExecutableWorkflow
            workflow = ExecutableWorkflow(**workflow_data)
            
            # Record usage
            usage = TemplateUsage(
                template_id=template_id,
                user_id=user_id,
                workflow_id=workflow.id,
                customizations=customizations or {}
            )
            
            await self._record_template_usage(usage)
            
            # Update usage count
            await self._increment_usage_count(template_id)
            
            return TemplateAdaptationResult(
                workflow_id=workflow.id,
                template_id=template_id,
                customizations_applied=customizations or {},
                success=True,
                message="Template successfully adapted to workflow"
            )
        
        except Exception as e:
            logger.error(f"Template adaptation failed: {e}")
            return TemplateAdaptationResult(
                workflow_id="",
                template_id=template_id,
                customizations_applied={},
                success=False,
                message=f"Template adaptation failed: {str(e)}"
            )
    
    # Ratings and Reviews
    
    @handle_errors
    async def rate_template(
        self,
        template_id: str,
        user_id: str,
        rating: int,
        review: Optional[str] = None
    ) -> TemplateRating:
        """Rate a workflow template."""
        # Check if template exists and is public
        template = await self.get_template(template_id)
        if not template or template.visibility != TemplateVisibility.PUBLIC:
            raise ValidationError("Template not found or not public")
        
        # Create rating
        template_rating = TemplateRating(
            template_id=template_id,
            user_id=user_id,
            rating=rating,
            review=review
        )
        
        # Store in database (upsert)
        query = """
            INSERT INTO template_ratings (id, template_id, user_id, rating, review, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (template_id, user_id)
            DO UPDATE SET rating = $4, review = $5, created_at = $6
            RETURNING *
        """
        
        await self.db.execute(
            query,
            template_rating.id,
            template_rating.template_id,
            template_rating.user_id,
            template_rating.rating,
            template_rating.review,
            template_rating.created_at
        )
        
        # Update template rating statistics
        await self._update_template_rating_stats(template_id)
        
        logger.info(f"User {user_id} rated template {template_id}: {rating}/5")
        return template_rating
    
    @handle_errors
    async def get_template_ratings(
        self,
        template_id: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[TemplateRating]:
        """Get ratings for a template."""
        query = """
            SELECT * FROM template_ratings 
            WHERE template_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        
        rows = await self.db.fetch(query, template_id, limit, offset)
        return [self._row_to_rating(row) for row in rows]
    
    # Community Statistics
    
    @handle_errors
    async def get_community_stats(self) -> CommunityStats:
        """Get community statistics."""
        # Total templates
        total_templates = await self.db.fetchval(
            "SELECT COUNT(*) FROM workflow_templates WHERE visibility = 'public' AND status = 'published'"
        )
        
        # Total users
        total_users = await self.db.fetchval(
            "SELECT COUNT(DISTINCT created_by) FROM workflow_templates WHERE visibility = 'public'"
        )
        
        # Total usage
        total_usage = await self.db.fetchval(
            "SELECT SUM(usage_count) FROM workflow_templates WHERE visibility = 'public'"
        )
        
        # Popular categories
        popular_categories = await self.db.fetch("""
            SELECT category, COUNT(*) as count
            FROM workflow_templates 
            WHERE visibility = 'public' AND status = 'published'
            GROUP BY category
            ORDER BY count DESC
            LIMIT 5
        """)
        
        # Top contributors
        top_contributors = await self.db.fetch("""
            SELECT created_by, COUNT(*) as template_count, SUM(usage_count) as total_usage
            FROM workflow_templates 
            WHERE visibility = 'public' AND status = 'published'
            GROUP BY created_by
            ORDER BY template_count DESC, total_usage DESC
            LIMIT 5
        """)
        
        # Recent templates
        recent_templates = await self.get_recent_templates(5)
        
        return CommunityStats(
            total_templates=total_templates or 0,
            total_users=total_users or 0,
            total_usage=total_usage or 0,
            popular_categories=[
                {"category": row["category"], "count": row["count"]}
                for row in popular_categories
            ],
            top_contributors=[
                {
                    "user_id": row["created_by"],
                    "template_count": row["template_count"],
                    "total_usage": row["total_usage"]
                }
                for row in top_contributors
            ],
            recent_templates=recent_templates
        )
    
    # Helper Methods
    
    def _row_to_template(self, row: Dict[str, Any]) -> WorkflowTemplate:
        """Convert database row to WorkflowTemplate."""
        return WorkflowTemplate(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            template_data=json.loads(row["template"]) if isinstance(row["template"], str) else row["template"],
            category=TemplateCategory(row["category"]),
            tags=row["tags"] or [],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            visibility=TemplateVisibility(row["visibility"]),
            status=TemplateStatus(row["status"]),
            usage_count=row["usage_count"],
            rating=row["rating"],
            rating_count=row["rating_count"],
            required_integrations=row["required_integrations"] or [],
            estimated_runtime=row["estimated_runtime"],
            complexity_level=row["complexity_level"]
        )
    
    def _row_to_rating(self, row: Dict[str, Any]) -> TemplateRating:
        """Convert database row to TemplateRating."""
        return TemplateRating(
            id=row["id"],
            template_id=row["template_id"],
            user_id=row["user_id"],
            rating=row["rating"],
            review=row["review"],
            created_at=row["created_at"]
        )
    
    async def _index_template_for_search(self, template: WorkflowTemplate):
        """Index template in vector database for search."""
        try:
            await self.vector_store.store(
                id=template.id,
                content={
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "category": template.category.value,
                    "tags": template.tags,
                    "complexity_level": template.complexity_level,
                    "required_integrations": template.required_integrations
                },
                collection_type="workflows"
            )
        except Exception as e:
            logger.error(f"Failed to index template {template.id}: {e}")
    
    async def _record_template_usage(self, usage: TemplateUsage):
        """Record template usage in database."""
        query = """
            INSERT INTO template_usage (id, template_id, user_id, workflow_id, used_at, customizations)
            VALUES ($1, $2, $3, $4, $5, $6)
        """
        
        await self.db.execute(
            query,
            usage.id,
            usage.template_id,
            usage.user_id,
            usage.workflow_id,
            usage.used_at,
            json.dumps(usage.customizations)
        )
    
    async def _increment_usage_count(self, template_id: str):
        """Increment usage count for a template."""
        query = "UPDATE workflow_templates SET usage_count = usage_count + 1 WHERE id = $1"
        await self.db.execute(query, template_id)
    
    async def _update_template_rating_stats(self, template_id: str):
        """Update rating statistics for a template."""
        query = """
            UPDATE workflow_templates 
            SET rating = (
                SELECT AVG(rating)::FLOAT FROM template_ratings WHERE template_id = $1
            ),
            rating_count = (
                SELECT COUNT(*) FROM template_ratings WHERE template_id = $1
            )
            WHERE id = $1
        """
        
        await self.db.execute(query, template_id)
    
    async def _generate_search_facets(self, search_query: TemplateSearchQuery) -> Dict[str, Any]:
        """Generate search facets for filtering."""
        # This would generate facet counts for categories, tags, etc.
        # For now, return empty facets
        return {
            "categories": [],
            "tags": [],
            "complexity_levels": [],
            "integrations": []
        }