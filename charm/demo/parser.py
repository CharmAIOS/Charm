from pathlib import Path
from typing import Any, Dict


def parse_fixture_to_uac(fixture_path: str) -> Dict[str, Any]:

    path = Path(fixture_path)

    return {
        "uac_version": "1.0",
        "framework": "crewai",
        "metadata": {
            "source": "crewai",
            "origin_file": str(path),
        },
        "agents": [
            {
                "id": "project_analyst",
                "persona": {
                    "name": "Project Analyst",
                    "description": "Analyzes project documents and market signals.",
                },
                "goals": ["Produce a concise project analysis report."],
                "capabilities": [
                    {"name": "web_search", "type": "tool"},
                    {"name": "file_writer", "type": "tool"},
                ],
            }
        ],
        "workflows": [
            {
                "id": "crewai_linear_flow",
                "nodes": ["n1_source", "n2_target"],
                "edges": [
                    {"from": "n1_source", "to": "n2_target"},
                ],
            }
        ],
    }

