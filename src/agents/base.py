"""Base agent definitions for the Natural Language Workflow Platform."""

from pydantic_ai import Agent, RunContext
from typing import TypeVar, Generic, Dict, Any, Optional, Union, Callable, List
from dataclasses import dataclass
from pydantic import BaseModel

from src.dependencies import WorkflowDependencies

T = TypeVar('T')
D = TypeVar('D')  # Dependency type
O = TypeVar('O')  # Output type


class BaseAgent(Generic[D, O]):
    """Base class for all workflow platform agents."""
    
    def __init__(
        self,
        model: str = "openai:gpt-4o",
        system_prompt: str = "",
        output_type: Optional[type] = None,
        deps_type: Optional[type] = None,
        retries: int = 3,
        instrument: bool = True,
        name: str = None
    ):
        """Initialize the base agent with common configuration."""
        self.name = name or self.__class__.__name__
        self.agent = Agent[D, O](
            model=model,
            deps_type=deps_type or WorkflowDependencies,
            output_type=output_type,
            system_prompt=system_prompt,
            retries=retries,
            instrument=instrument
        )
    
    async def run(
        self,
        prompt: str,
        deps: Optional[D] = None,
        **kwargs
    ) -> O:
        """Run the agent with the given prompt and dependencies."""
        if deps is None and issubclass(self.agent.deps_type, WorkflowDependencies):
            async with get_dependencies() as default_deps:
                return await self.agent.run(prompt, deps=default_deps, **kwargs)
        return await self.agent.run(prompt, deps=deps, **kwargs)
    
    def add_tool(self, func: Callable) -> Callable:
        """Add a tool to the agent."""
        return self.agent.tool(func)
    
    def add_system_prompt(self, func: Callable) -> Callable:
        """Add a dynamic system prompt to the agent."""
        return self.agent.system_prompt(func)
    
    def add_instructions(self, func: Callable) -> Callable:
        """Add dynamic instructions to the agent."""
        return self.agent.instructions(func)
    
    def add_output_validator(self, func: Callable) -> Callable:
        """Add an output validator to the agent."""
        return self.agent.output_validator(func)


@dataclass
class AgentResult(Generic[O]):
    """Result from an agent execution."""
    output: O
    confidence: float = 1.0
    metadata: Dict[str, Any] = None


class AgentRegistry:
    """Registry for all agents in the platform."""
    
    _agents: Dict[str, BaseAgent] = {}
    
    @classmethod
    def register(cls, agent: BaseAgent) -> BaseAgent:
        """Register an agent in the registry."""
        cls._agents[agent.name] = agent
        return agent
    
    @classmethod
    def get(cls, name: str) -> Optional[BaseAgent]:
        """Get an agent by name."""
        return cls._agents.get(name)
    
    @classmethod
    def list_agents(cls) -> List[str]:
        """List all registered agents."""
        return list(cls._agents.keys())


# Import at the end to avoid circular imports
from src.dependencies import get_dependencies