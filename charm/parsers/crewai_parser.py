import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List
from jsonschema import validate

class CrewAIParser:
    def __init__(self, schema_path: str = "docs/contracts/uac/schema.json"):
        self.schema = json.loads(Path(schema_path).read_text())

    # ------------------------------------------------------------
    # Load CrewAI fixture dynamically
    # ------------------------------------------------------------
    def load_fixture(self, fixture_path: str):
        spec = importlib.util.spec_from_file_location("crewai_fixture", fixture_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
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
        if not crew:
            raise ValueError("No Crew object found in fixture")

        # -----------------------------
        # Normalize agents
        # -----------------------------
        uac_agents = []
        for agent in agents:
            uac_agents.append(self._convert_agent(agent))

        # -----------------------------
        # Normalize workflow
        # -----------------------------
        workflow = self._convert_workflow(crew, agents)

        # -----------------------------
        # Full UAC dict
        # -----------------------------
        uac = {
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
    def _collect_agents(self, objects: List[Any]):
        return [o for o in objects if o.__class__.__name__ == "Agent"]

    def _collect_crew(self, objects: List[Any]):
        crews = [o for o in objects if o.__class__.__name__ == "Crew"]
        return crews[0] if crews else None

    # ------------------------------------------------------------
    # Agent → UAC Agent
    # ------------------------------------------------------------
    def _convert_agent(self, agent: Any) -> Dict[str, Any]:
        name = getattr(agent, "name", "Unnamed Agent")
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
            "goals": [goal],
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
    # Workflow (agents in execution order)
    # ------------------------------------------------------------
    def _convert_workflow(self, crew: Any, agents: List[Any]) -> Dict[str, Any]:
        agent_names = [getattr(a, "name", a.__class__.__name__) for a in agents]
        # Build linear edges (naive but acceptable for this fixture)
        edges = []
        for i in range(len(agent_names) - 1):
            edges.append({"from": agent_names[i], "to": agent_names[i + 1]})
        return {
            "id": "crewai_workflow",
            "nodes": agent_names,
            "edges": edges,
        }
