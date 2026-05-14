import sys
import yaml
from pathlib import Path
from src.charm.contracts.uac import CharmConfig

def main():
    templates_dir = Path("src/charm/templates")
    has_error = False
    for yaml_file in templates_dir.glob("*.yaml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        try:
            CharmConfig.model_validate(data)
            print(f"OK: {yaml_file.name}")
        except Exception as e:
            print(f"FAIL: {yaml_file.name}")
            print(e)
            has_error = True
    sys.exit(1 if has_error else 0)

if __name__ == "__main__":
    main()
