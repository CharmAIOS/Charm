# Charm – Dev Setup Guide

This document helps you get a local Charm dev environment running and verify
that the first fixture-based flow works end-to-end.

1. Prerequisites
- Python **3.10+**
- `git`
- Recommended: a virtual environment tool (`python -m venv`, `conda`, or similar)

2. Fork & Clone the Repository
```bash
git clone https://github.com/CharmAIOS/Charm.git
cd Charm
```   
3. Create and Activate a Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
``` 
4. Install Python Dependencies
```bash
pip install -r requirements.txt
```
5. Run the Sample Fixture

Charm ships with a small CrewAI-based sample agent that we use as a fixture
for the first route (CrewAI → LangGraph).

To run the original CrewAI agent:
```bash
python docs/examples/crewai_research_agent.py
```
This should:
- Import the fixture agent from docs/fixtures/crewai-research-agent/agents.py
- Execute the CrewAI flow using your local environment configuration

6. Run the Smoke Tests

Charm includes a minimal test to verify that the fixture is present and importable.
```bash
python -m pytest tests/fixtures/test_fixture_smoke.py
```

Useful paths when you start contributing:
- docs/fixtures/crewai-research-agent
- tests/fixtures/test_fixture_smoke.py
- docs/pipeline.md
- docs/contracts/uac
