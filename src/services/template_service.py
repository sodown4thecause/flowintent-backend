"""
Service for managing workflow templates.
"""
import json
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncpg
from fastapi import HTTPException

from src.models.template import (
    N8nWorkflowTemplate, 
    N8nTemplateSearchResult,
    N8nTemplateImport,
    N8nTemplateExport
)
from src.models.community import WorkflowTemplate
from src.services.vector_store import VectorStoreService


class TemplateService:
    """Service for managing workflow templates."""
    
    def __init__(self, db_pool, vector_store_service: VectorStoreService):
        """Initialize the template service."""
        self.db_pool = db_pool
        self.vector_store = vector_store_service
        
    async def create_template(self, template: WorkflowTemplate) -> str:
        """Create a new workflow template."""
        async with self.db_pool.acquire() as conn:
            template_id = await conn.fetchval(
                """
                INSERT INTO workflow_templates (
                    id, name, description, category, tags, nodes, connections, 
                    created_at, updated_at, author_id, author_name, version,
                    requirements, setup_instructions, example_prompts,
                    nl_description, nl_steps, nl_requirements
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                ) RETURNING id
                """,
                template.id,
                template.name,
                template.description,
                template.category,
                template.tags,
                json.dumps([node.dict() for node in template.nodes]),
                json.dumps(template.connections),
                template.created_at,
                template.updated_at,
                template.author_id,
                template.author_name,
                template.version,
                json.dumps(template.requirements),
                template.setup_instructions,
                template.example_prompts,
                template.nl_description,
                template.nl_steps,
                template.nl_requirements
            )
            
            # Create vector embedding for semantic search
            await self.vector_store.store_template_embedding(
                template_id=template.id,
                text=f"{template.name} {template.description} {template.nl_description} {' '.join(template.tags)} {' '.join(template.example_prompts)}",
                metadata={
                    "name": template.name,
                    "description": template.description,
                    "category": template.category,
                    "tags": template.tags,
                    "author_name": template.author_name,
                }
            )
            
            return template_id
    
    async def get_template(self, template_id: str) -> WorkflowTemplate:
        """Get a workflow template by ID."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM workflow_templates WHERE id = $1
                """,
                template_id
            )
            
            if not row:
                raise HTTPException(status_code=404, detail="Template not found")
                
            return self._row_to_template(row)
    
    async def search_templates(self, query: str, category: Optional[str] = None, 
                              tags: Optional[List[str]] = None, limit: int = 10) -> List[WorkflowTemplateSearchResult]:
        """Search for workflow templates using semantic search."""
        # Get vector search results
        search_results = await self.vector_store.search_templates(
            query_text=query,
            limit=limit * 2  # Get more results than needed for filtering
        )
        
        # Filter results by category and tags if provided
        filtered_results = []
        for result in search_results:
            metadata = result.metadata
            
            # Filter by category if provided
            if category and metadata.get("category") != category:
                continue
                
            # Filter by tags if provided
            if tags and not all(tag in metadata.get("tags", []) for tag in tags):
                continue
                
            filtered_results.append(
                WorkflowTemplateSearchResult(
                    template_id=result.id,
                    name=metadata.get("name", "Unknown"),
                    description=metadata.get("description", ""),
                    category=metadata.get("category", "Other"),
                    tags=metadata.get("tags", []),
                    similarity_score=result.score,
                    author_name=metadata.get("author_name")
                )
            )
            
            if len(filtered_results) >= limit:
                break
                
        return filtered_results
    
    async def import_template(self, import_request: WorkflowTemplateImport) -> Dict[str, Any]:
        """Import a workflow template for a user."""
        # Get the template
        template = await self.get_template(import_request.template_id)
        
        # Create a new workflow from the template
        async with self.db_pool.acquire() as conn:
            # Apply customizations if provided
            if import_request.customizations:
                # Apply customizations to the template
                # This would modify nodes, connections, etc. based on user preferences
                pass
                
            # Create the workflow
            workflow_id = await conn.fetchval(
                """
                INSERT INTO workflows (
                    user_id, name, description, workflow_data, status, 
                    created_at, updated_at, template_id
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8
                ) RETURNING id
                """,
                import_request.user_id,
                template.name,
                template.description,
                json.dumps({
                    "nodes": [node.dict() for node in template.nodes],
                    "connections": template.connections
                }),
                "draft",
                datetime.now(),
                datetime.now(),
                template.id
            )
            
            return {
                "workflow_id": workflow_id,
                "name": template.name,
                "status": "draft",
                "message": f"Successfully imported template '{template.name}'"
            }
    
    async def export_as_template(self, export_request: WorkflowTemplateExport) -> str:
        """Export a workflow as a template."""
        async with self.db_pool.acquire() as conn:
            # Get the workflow
            workflow_row = await conn.fetchrow(
                """
                SELECT * FROM workflows WHERE id = $1
                """,
                export_request.workflow_id
            )
            
            if not workflow_row:
                raise HTTPException(status_code=404, detail="Workflow not found")
                
            # Get user info
            user_row = await conn.fetchrow(
                """
                SELECT * FROM users WHERE id = $1
                """,
                workflow_row["user_id"]
            )
            
            if not user_row:
                raise HTTPException(status_code=404, detail="User not found")
                
            # Create template from workflow
            workflow_data = json.loads(workflow_row["workflow_data"])
            
            template = WorkflowTemplate(
                name=export_request.name,
                description=export_request.description,
                category=export_request.category,
                tags=export_request.tags,
                nodes=workflow_data.get("nodes", []),
                connections=workflow_data.get("connections", {}),
                author_id=workflow_row["user_id"],
                author_name=user_row["name"],
                nl_description=export_request.nl_description,
                nl_steps=export_request.nl_steps,
                nl_requirements=export_request.nl_requirements,
                example_prompts=export_request.example_prompts
            )
            
            # Create the template
            template_id = await self.create_template(template)
            
            # If make_public is True, mark the template as public
            if export_request.make_public:
                await conn.execute(
                    """
                    UPDATE workflow_templates SET is_public = TRUE WHERE id = $1
                    """,
                    template_id
                )
                
            return template_id
    
    async def get_featured_templates(self, limit: int = 10) -> List[WorkflowTemplateSearchResult]:
        """Get featured workflow templates."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, category, tags, author_name
                FROM workflow_templates
                WHERE is_public = TRUE
                ORDER BY featured_score DESC, created_at DESC
                LIMIT $1
                """,
                limit
            )
            
            return [
                WorkflowTemplateSearchResult(
                    template_id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    category=row["category"],
                    tags=row["tags"],
                    similarity_score=1.0,  # Not based on search
                    author_name=row["author_name"]
                )
                for row in rows
            ]
    
    async def get_templates_by_category(self, category: str, limit: int = 10) -> List[WorkflowTemplateSearchResult]:
        """Get workflow templates by category."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, description, category, tags, author_name
                FROM workflow_templates
                WHERE category = $1 AND is_public = TRUE
                ORDER BY created_at DESC
                LIMIT $2
                """,
                category,
                limit
            )
            
            return [
                WorkflowTemplateSearchResult(
                    template_id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    category=row["category"],
                    tags=row["tags"],
                    similarity_score=1.0,  # Not based on search
                    author_name=row["author_name"]
                )
                for row in rows
            ]
    
    async def seed_templates_from_directory(self, directory_path: str) -> int:
        """Seed templates from JSON files in a directory."""
        count = 0
        
        for filename in os.listdir(directory_path):
            if not filename.endswith('.json'):
                continue
                
            file_path = os.path.join(directory_path, filename)
            
            try:
                with open(file_path, 'r') as f:
                    template_data = json.load(f)
                    
                # Extract template name from filename
                template_name = filename.replace('.json', '').replace('_', ' ')
                
                # Create basic template object
                template = self._convert_n8n_to_template(
                    n8n_data=template_data,
                    name=template_name
                )
                
                # Create the template
                await self.create_template(template)
                count += 1
                
            except Exception as e:
                print(f"Error importing template {filename}: {str(e)}")
                
        return count
    
    def _row_to_template(self, row) -> WorkflowTemplate:
        """Convert a database row to a WorkflowTemplate object."""
        return WorkflowTemplate(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            category=row["category"],
            tags=row["tags"],
            nodes=json.loads(row["nodes"]),
            connections=json.loads(row["connections"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            author_id=row["author_id"],
            author_name=row["author_name"],
            version=row["version"],
            requirements=json.loads(row["requirements"]) if row["requirements"] else {},
            setup_instructions=row["setup_instructions"],
            example_prompts=row["example_prompts"],
            nl_description=row["nl_description"],
            nl_steps=row["nl_steps"],
            nl_requirements=row["nl_requirements"]
        )
    
    def _convert_n8n_to_template(self, n8n_data: Dict[str, Any], name: str) -> WorkflowTemplate:
        """Convert n8n workflow data to our template format."""
        # Extract nodes
        nodes = []
        for node_data in n8n_data.get("nodes", []):
            # Skip sticky notes
            if node_data.get("type") == "n8n-nodes-base.stickyNote":
                continue
                
            # Extract node position
            position = WorkflowNodePosition(
                x=node_data.get("position", [0, 0])[0],
                y=node_data.get("position", [0, 0])[1]
            )
            
            # Extract credentials
            credentials = {}
            if "credentials" in node_data:
                for cred_type, cred_data in node_data["credentials"].items():
                    credentials[cred_type] = WorkflowNodeCredential(
                        id=cred_data.get("id", ""),
                        name=cred_data.get("name", "")
                    )
            
            # Create node
            node = WorkflowNode(
                id=node_data.get("id", ""),
                name=node_data.get("name", ""),
                type=node_data.get("type", ""),
                position=position,
                parameters=node_data.get("parameters", {}),
                disabled=node_data.get("disabled", False),
                credentials=credentials if credentials else None,
                type_version=node_data.get("typeVersion", 1.0)
            )
            
            nodes.append(node)
        
        # Extract connections
        connections = n8n_data.get("connections", {})
        
        # Extract description and steps from sticky notes if available
        nl_description = "A workflow template imported from n8n."
        nl_steps = []
        nl_requirements = []
        
        for node_data in n8n_data.get("nodes", []):
            if node_data.get("type") == "n8n-nodes-base.stickyNote":
                content = node_data.get("parameters", {}).get("content", "")
                
                # Check if this is a description sticky note
                if "What it does" in content:
                    nl_description = content.split("What it does")[1].split("##")[0].strip()
                
                # Check if this is a steps sticky note
                if "How it works" in content:
                    steps_section = content.split("How it works")[1].split("##")[0].strip()
                    for line in steps_section.split("\n"):
                        if line.strip() and not line.startswith("#"):
                            nl_steps.append(line.strip())
                
                # Check if this is a requirements sticky note
                if "Requirements" in content:
                    reqs_section = content.split("Requirements")[1].split("##")[0].strip()
                    for line in reqs_section.split("\n"):
                        if line.strip() and line.startswith("-"):
                            nl_requirements.append(line.strip()[1:].strip())
        
        # Determine category based on node types
        category = "Other"
        node_types = [node.type for node in nodes]
        
        if any("telegram" in node_type.lower() for node_type in node_types):
            category = "Messaging"
        elif any("openai" in node_type.lower() for node_type in node_types):
            category = "AI"
        elif any("http" in node_type.lower() for node_type in node_types):
            category = "API"
        elif any("google" in node_type.lower() for node_type in node_types):
            category = "Google"
        
        # Extract tags from node types
        tags = []
        for node_type in node_types:
            parts = node_type.lower().split(".")
            if len(parts) > 1:
                tag = parts[1].replace("nodes", "").strip()
                if tag and tag not in tags:
                    tags.append(tag)
        
        # Add AI tag if using AI nodes
        if any("ai" in node_type.lower() or "openai" in node_type.lower() or "gpt" in node_type.lower() for node_type in node_types):
            if "ai" not in tags:
                tags.append("ai")
        
        # Create template
        return WorkflowTemplate(
            name=name,
            description=f"Imported n8n workflow: {name}",
            category=category,
            tags=tags,
            nodes=nodes,
            connections=connections,
            author_id=None,
            author_name="n8n Import",
            nl_description=nl_description,
            nl_steps=nl_steps or ["This workflow was imported from n8n."],
            nl_requirements=nl_requirements or ["n8n workflow import"],
            example_prompts=[
                f"Create a workflow like {name}",
                f"I need a workflow that does {nl_description}"
            ]
        )