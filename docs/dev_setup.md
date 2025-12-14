## Charm – Dev Setup Guide

1. Prerequisites
- Python **3.10+**
- `git`
- [uv](https://github.com/astral-sh/uv)

2. Fork & Clone
```bash
git clone https://github.com/CharmAIOS/Charm.git
cd Charm
```   
3. Create virtual environment
```bash
uv venv
source .venv/bin/activate
``` 
4. Install
```bash
uv pip install -e ".[dev]"
```
5. Run Tests
```bash
pytest
```
