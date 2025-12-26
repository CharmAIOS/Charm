import json
from pathlib import Path

from charm.parsers.crewai_parser import CrewAIParser

FIXTURE = Path("docs/fixtures/crewai-research-agent/agents.py")
GOLDEN = Path("docs/fixtures/crewai-research-agent/uac.sample.json")


def test_crewai_parser_basic_fields():
    """Run the CrewAIParser on the canonical fixture and assert basic mappings."""
    parser = CrewAIParser(validate_schema=False)
    parsed = parser.parse_from_path(FIXTURE)

    # Load golden for reference
    golden = json.loads(GOLDEN.read_text())

    # Persona name should map from the agent's role/name
    assert parsed.get("agents"), "No agents parsed"
    first = parsed["agents"][0]
    assert first["persona"]["name"] == golden["persona"]["name"]

    # At least one of the golden goals should appear in parsed agent goals
    assert any(g in first.get("goals", []) for g in golden.get("goals", []))

    # Workflow should contain nodes referencing the agent id
    wf = parsed.get("workflows", [])[0]
    assert any(first["id"] in n for n in wf.get("nodes", []))


def test_crewai_parser_normalizes_to_schema():
    """Normalize parser output into per-agent UAC objects and validate against schema."""
    from jsonschema import validate

    parser = CrewAIParser(validate_schema=False)
    parsed = parser.parse_from_path(FIXTURE)

    schema = json.loads(Path("docs/contracts/uac/schema.json").read_text())

    # For each parsed agent produce a schema-shaped UAC and validate
    for agent in parsed.get("agents", []):
        uac = {
            "version": "0.1.0",
            "persona": agent.get("persona", {"name": "unnamed"}),
            "goals": agent.get("goals", []),
            # schema expects capabilities as strings; map from parser capabilities if present
            "capabilities": [
                c.get("name") if isinstance(c, dict) else str(c)
                for c in agent.get("capabilities", [])
            ],
        }

        # validate will raise if not matching
        validate(instance=uac, schema=schema)
