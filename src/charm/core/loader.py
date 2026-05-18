import os
import sys

import yaml  # type: ignore

if sys.version_info >= (3, 10):
    from importlib.metadata import entry_points
else:
    from importlib_metadata import entry_points  # type: ignore

from ..adapters.base import BaseAdapter
from ..contracts.uac import CharmConfig
from .errors import CharmConfigError, CharmValidationError
from .logger import logger
from .utils import dynamic_import
from .wrapper import CharmWrapper


class CharmLoader:
    """Responsible for bootstrapping the agent from the file system."""

    @staticmethod
    def load(project_path: str) -> CharmWrapper:
        logger.info(f"Loading Charm project from: {project_path}")

        # Load Configuration
        yaml_path = os.path.join(project_path, "charm.yaml")
        if not os.path.exists(yaml_path):
            raise CharmConfigError(f"Missing charm.yaml in {project_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)
            # Validate against UAC Pydantic model
            config = CharmConfig(**raw_data)
        except Exception as e:
            raise CharmValidationError(f"Invalid charm.yaml: {e}") from e

        adapter_type = config.runtime.adapter.type
        logger.debug(f"Detected adapter: {adapter_type}")

        adapter: BaseAdapter

        # Adapter Selection Logic via entry_points
        eps = entry_points(group="charm.adapters")
        adapter_ep = next((ep for ep in eps if ep.name == adapter_type), None)

        if not adapter_ep:
            raise CharmValidationError(
                f"Unsupported adapter type: '{adapter_type}'. "
                "Ensure the adapter package is installed and registered in 'charm.adapters' entry points."
            )

        try:
            AdapterClass = adapter_ep.load()
        except Exception as e:
            raise CharmValidationError(f"Failed to load adapter '{adapter_type}': {e}") from e

        if adapter_type == "openclaw":
            adapter = AdapterClass(config=config)

        elif adapter_type == "node":
            if not config.runtime.adapter.entry_point:
                raise CharmValidationError(
                    "Node adapter requires 'entry_point' (e.g. 'npm start')."
                )
            adapter = AdapterClass(command=config.runtime.adapter.entry_point)

        else:
            if not config.runtime.adapter.entry_point:
                raise CharmValidationError(
                    f"{adapter_type} adapter requires 'entry_point' (python path)."
                )

            agent_instance = dynamic_import(config.runtime.adapter.entry_point, project_path)
            
            # Instantiate adapter (third party adapters follow this pattern)
            try:
                adapter = AdapterClass(agent_instance=agent_instance, config=config)
            except TypeError:
                # Fallback to single argument
                adapter = AdapterClass(agent_instance)

        # Return the standardized wrapper
        return CharmWrapper(adapter=adapter, config=config)
