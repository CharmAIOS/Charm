import importlib
import sys
import os
from typing import Any
from .errors import CharmConfigError

def dynamic_import(entry_point: str, project_path: str) -> Any:
    """
    Dynamically imports a Python object from a string reference.
    Format: "module.submodule:variable"
    """
    if ":" not in entry_point:
        raise CharmConfigError(f"Invalid entry_point format: '{entry_point}'. Expected 'module:variable'")
    
    module_name, obj_name = entry_point.split(":")
    
    # 確保路徑是絕對路徑
    abs_path = os.path.abspath(project_path)
    
    # 🔥 優化：避免重複加入路徑，保持 sys.path 乾淨
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
    
    try:
        # 嘗試載入模組
        module = importlib.import_module(module_name)
        
        # 嘗試從模組中取得物件 (變數、函數或類別)
        if not hasattr(module, obj_name):
            raise CharmConfigError(
                f"Module '{module_name}' loaded successfully, but attribute '{obj_name}' was not found. "
                f"Available attributes: {dir(module)[:10]}..." # 顯示部分屬性幫忙除錯
            )
        return getattr(module, obj_name)
        
    except ImportError as e:
        # 捕捉 Import 錯誤 (例如用戶忘了裝套件，或檔名打錯)
        raise CharmConfigError(f"Could not import module '{module_name}'. check your requirements or filename: {e}")
    except Exception as e:
        # 捕捉執行期錯誤 (例如 module 裡面有 Syntax Error)
        raise CharmConfigError(f"Failed to load agent object from '{entry_point}': {e}", original_error=e)