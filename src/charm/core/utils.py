import importlib
import sys
import os
from typing import Any
from .errors import CharmConfigError

def dynamic_import(entry_point: str, project_path: str) -> Any:
    if ":" not in entry_point:
        raise CharmConfigError(f"Invalid entry_point format: '{entry_point}'. Expected 'module:variable'")
    
    module_name, obj_name = entry_point.split(":")
    
    abs_path = os.path.abspath(project_path)
    
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
    
    try:
        module = importlib.import_module(module_name)
        
        if not hasattr(module, obj_name):
            raise CharmConfigError(
                f"Module '{module_name}' loaded successfully, but attribute '{obj_name}' was not found. "
                f"Available attributes: {dir(module)[:10]}..." 
            )
        return getattr(module, obj_name)
        
    except ImportError as e:
        raise CharmConfigError(f"Could not import module '{module_name}'. check your requirements or filename: {e}")
    except Exception as e:
        raise CharmConfigError(f"Failed to load agent object from '{entry_point}': {e}", original_error=e)