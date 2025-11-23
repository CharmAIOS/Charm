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
source .venv/bin/activate
``` 
4. Install Charm with development dependencies
```bash
pip install -e ".[dev]" && pre-commit install
```
5. Run the demo
```bash
python -m charm.demo.run
```
6. Run Tests
```bash
pytest
```

Useful paths when you start contributing:
- docs/fixtures/crewai-research-agent
- tests/fixtures/test_fixture_smoke.py
- docs/pipeline.md
- docs/contracts/uac
