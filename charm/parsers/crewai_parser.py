import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Union

from jsonschema import validate

DEFAULT_SCHEMA_PATH = Path("docs/contracts/uac/schema.json")


class CrewAIParser:
    """
    v0 CrewAI → UAC Parser

    - Dynamically loads a CrewAI fixture (agents.py)
    - Collects Agent and Crew objects
    - Normalizes them into a UAC dictionary
    - Validates the output against the UAC schema
    """

    def __init__(self, schema_path: Union[str, Path] = DEFAULT_SCHEMA_PATH) -> None:
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(
                f"UAC schema not found at {schema_path}. "
                "Expected docs/contracts/uac/schema.json."
            )
        self.schema_path = schema_path
        self.schema: Dict[str, Any] = json.loads(self.schema_path.read_text())

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------
    def parse_from_path(self, fixture_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Convenience method for demo/testing.
        Example:
            parser.parse_from_path('fixtures/crewai-research-agent/agents.py')
        """
        module = self.load_fixture(fixture_path)
        return self.parse(module)

    # ------------------------------------------------------------
    # Load CrewAI fixture dynamically
    # ------------------------------------------------------------
    def load_fixture(self, fixture_path: Union[str, Path]) -> Any:
        fixture_path = Path(fixture_path)

        if not fixture_path.exists():
            raise FileNotFoundError(f"CrewAI fixture not found at {fixture_path}")

        spec = importlib.util.spec_from_file_location("crewai_fixture", fixture_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load module spec for: {fixture_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[arg-type]

        return module

    # ------------------------------------------------------------
    # Main parser — convert CrewAI → UAC
    # ------------------------------------------------------------
    def parse(self, fixture_module: Any) -> Dict[str, Any]:
        objects = [getattr(fixture_module, name) for name in dir(fixture_module)]
        agents = self._collect_agents(objects)
        crew = self._collect_crew(objects)

        if not agents:
            raise ValueError("No Agent objects found in CrewAI fixture")
        if crew is None:
            raise ValueError("No Crew object found in CrewAI fixture")

        # Normalize agents
        uac_agents = [self._convert_agent(agent) for agent in agents]

        # Normalize workflow (v0: simple linear order)
        workflow = self._convert_workflow(crew, agents)

        # Construct the UAC object (must match the UAC schema)
        uac: Dict[str, Any] = {
            "uac_version": "1.0",
            "framework": "crewai",
            "agents": uac_agents,
            "workflows": [workflow],
            "metadata": {
                "source": "crewai",
                "origin_file": getattr(fixture_module, "__file__", None),
            },
        }

        # Validate against schema
        validate(instance=uac, schema=self.schema)

        return uac

    # ------------------------------------------------------------
    # Collectors
    # ------------------------------------------------------------
    def _collect_agents(self, objects: List[Any]) -> List[Any]:
        return [o for o in objects if o.__class__.__name__ == "Agent"]

    def _collect_crew(self, objects: List[Any]) -> Any:
        crews = [o for o in objects if o.__class__.__name__ == "Crew"]
        return crews[0] if crews else None

    # ------------------------------------------------------------
    # Agent → UAC Agent
    # ------------------------------------------------------------
    def _convert_agent(self, agent: Any) -> Dict[str, Any]:
        name = getattr(agent, "name", None) or getattr(agent, "role", "Unnamed Agent")
        role = getattr(agent, "role", "")
        persona = getattr(agent, "backstory", role)
        goal = getattr(agent, "goal", "")
        tools = getattr(agent, "tools", [])

        return {
            "id": name.lower().replace(" ", "_"),
            "persona": {
                "name": name,
                "description": persona,
            },
            "goals": [goal] if goal else [],
            "capabilities": [
                {
                    "name": t.__class__.__name__,
                    "type": "tool",
                    "metadata": {
                        "origin": "crewai",
                        "class": t.__class__.__name__,
                    },
                }
                for t in tools
            ],
            "raw_framework_data": {
                "repr": repr(agent),
                "attributes": {
                    k: str(getattr(agent, k))
                    for k in dir(agent)
                    if not k.startswith("_")
                },
            },
        }

    # ------------------------------------------------------------
    # Workflow (v0: simple sequential workflow)
    # ------------------------------------------------------------
    def _convert_workflow(self, crew: Any, agents: List[Any]) -> Dict[str, Any]:
        agent_ids = [
            (getattr(a, "name", None) or getattr(a, "role", a.__class__.__name__))
            for a in agents
        ]

        edges: List[Dict[str, str]] = []
        for i in range(len(agent_ids) - 1):
            edges.append({"from": agent_ids[i], "to": agent_ids[i + 1]})

        return {
            "id": "crewai_workflow",
            "nodes": agent_ids,
            "edges": edges,
        }
