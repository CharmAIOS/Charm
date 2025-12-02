from typing import Any, Dict


class RuntimeB:


    name = "RuntimeB (LangGraph Mock)"

    def execute(self, node_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[{self.name}] Executing node: {node_id}")
        context.setdefault("trace", []).append(
            {"runtime": "RuntimeB", "node": node_id}
        )
        return {
            "status": "ok",
            "node": node_id,
            "runtime": "RuntimeB",
            "context": context,
        }

