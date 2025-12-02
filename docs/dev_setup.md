# Charm – Dev Setup Guide

1. Prerequisites
- Python **3.10+**
- `git`

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
pip install -e ".[dev]"
```
5. Run the demo
```bash
python src/charm/demo/demo_mock.py  # python -m charm.demo.demo_mock
```
6. Run Tests
```bash
pytest
```
