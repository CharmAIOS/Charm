from typing import Any, Dict


class RuntimeA:


    name = "RuntimeA (CrewAI Mock)"

    def execute(self, node_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[{self.name}] Executing node: {node_id}")
        # Append a trace into context
        context.setdefault("trace", []).append(
            {"runtime": "RuntimeA", "node": node_id}
        )
        # Return new partial result
        return {
            "status": "ok",
            "node": node_id,
            "runtime": "RuntimeA",
            "context": context,
        }

