from typing import Any, Dict, Tuple


def render_uac_to_langgraph(uac: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:

    agents = uac.get("agents", [])
    workflows = uac.get("workflows", [])
    workflow = workflows[0] if workflows else {"nodes": [], "edges": []}

    profile = {
        "kind": "langgraph_profile",
        "runtime": "mock-langgraph",
        "nodes": workflow.get("nodes", []),
        "edges": workflow.get("edges", []),
        "metadata": {
            "source_framework": uac.get("framework"),
            "uac_version": uac.get("uac_version"),
        },
    }

    mapping_report = {
        "summary": "Mock mapping completed.",
        "equivalent_fields": ["agents", "workflows"],
        "degraded_fields": [],
        "skipped_fields": [],
        "notes": [
            "This is a mock mapping report for demo purposes.",
            "No real LangGraph schema is involved yet.",
        ],
    }

    return profile, mapping_report

