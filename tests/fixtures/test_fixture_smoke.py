from pathlib import Path
import importlib.util

# Path: fixtures/crewai-research-agent/agents.py
FIXTURE_AGENT_PATH = Path("fixtures/crewai-research-agent/agents.py")


def test_fixture_agents_exist():
    """Ensure the CrewAI fixture file exists."""
    assert FIXTURE_AGENT_PATH.exists(), "Fixture agents.py not found at expected path"


def test_fixture_importable():
    """Ensure the fixture agents.py can be imported and exposes project_analyst."""
    spec = importlib.util.spec_from_file_location(
        "fixture_agents",
        FIXTURE_AGENT_PATH,
    )
    assert spec is not None and spec.loader is not None, "Failed to load fixture module spec"

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[arg-type]

    assert hasattr(mod, "project_analyst"), "Agent 'project_analyst' missing in fixture"
