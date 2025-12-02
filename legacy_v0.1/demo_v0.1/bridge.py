from typing import Any, Dict, List, Optional


class ExecutionBridge:


    def __init__(self) -> None:
        pass

    def run(
        self,
        stategraph: Dict[str, Any],
        runtime_a: Any,
        runtime_b: Any,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        nodes: List[str] = stategraph.get("nodes", [])
        context: Dict[str, Any] = initial_context or {}

        print("[Bridge] Starting execution over mock stategraph...")

        if not nodes:
            print("[Bridge] No nodes to execute.")
            return {"status": "empty", "context": context}

        # First node on RuntimeA
        first_node = nodes[0]
        print(f"[Bridge] Dispatching first node to RuntimeA: {first_node}")
        result_a = runtime_a.execute(first_node, context)
        context = result_a.get("context", context)

        # Second node (if exists) on RuntimeB
        if len(nodes) > 1:
            second_node = nodes[1]
            print(f"[Bridge] Forwarding second node to RuntimeB: {second_node}")
            result_b = runtime_b.execute(second_node, context)
            context = result_b.get("context", context)
            final_result = result_b
        else:
            final_result = result_a

        print("[Bridge] Execution complete.")
        return {
            "status": "done",
            "final_result": final_result,
            "context": context,
        }

