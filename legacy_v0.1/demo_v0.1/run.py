from pathlib import Path

from .parser import parse_fixture_to_uac
from .renderer import render_uac_to_langgraph
from .loader import load_profile_to_stategraph
from .runtime_a import RuntimeA
from .runtime_b import RuntimeB
from .bridge import ExecutionBridge


def main() -> None:
    print("=== Charm Working Demo (Mock Pipeline) ===")

    # 1. Mock input: fixture path (we won't really parse it yet)
    fixture_path = Path("docs/fixtures/crewai-research-agent/agents.py")
    print(f"[Demo] Using fixture: {fixture_path}")

    # 2. Parser → UAC
    print("[Demo] Step 1: Parser → UAC")
    uac = parse_fixture_to_uac(str(fixture_path))
    print(f"[Demo] UAC created: framework={uac.get('framework')}, agents={len(uac.get('agents', []))}")

    # 3. Renderer → LangGraph Profile + Mapping Report
    print("[Demo] Step 2: Renderer → LangGraph Profile")
    profile, mapping_report = render_uac_to_langgraph(uac)
    print(f"[Demo] Profile nodes={len(profile.get('nodes', []))}, edges={len(profile.get('edges', []))}")
    print(f"[Demo] Mapping summary: {mapping_report.get('summary')}")

    # 4. Loader → StateGraph
    print("[Demo] Step 3: Loader → StateGraph")
    stategraph = load_profile_to_stategraph(profile)
    print(f"[Demo] StateGraph id={stategraph.get('id')}")

    # 5. Runtimes + Bridge execution
    print("[Demo] Step 4: Bridge → Cross-runtime execution")
    runtime_a = RuntimeA()
    runtime_b = RuntimeB()
    bridge = ExecutionBridge()

    result = bridge.run(
        stategraph=stategraph,
        runtime_a=runtime_a,
        runtime_b=runtime_b,
        initial_context={"demo": True},
    )

    print("[Demo] Final result status:", result.get("status"))
    print("[Demo] Final context trace:", result.get("context", {}).get("trace", []))
    print("=== Demo Finished ===")


if __name__ == "__main__":
    main()

