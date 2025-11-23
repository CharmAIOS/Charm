from typing import Any, Dict


def load_profile_to_stategraph(profile: Dict[str, Any]) -> Dict[str, Any]:

    nodes = profile.get("nodes", [])
    edges = profile.get("edges", [])

    return {
        "id": "mock_stategraph",
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "runtime": profile.get("runtime"),
            "kind": "mock_stategraph",
        },
    }

