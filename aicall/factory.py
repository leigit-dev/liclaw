import importlib
import pkgutil
import traceback
from typing import List, Dict, Any
from .base import AIBackend

BACKENDS_PACKAGE = "aicall.backends"

def _discover_backends() -> List[Dict[str, Any]]:
    backends = []
    try:
        package = importlib.import_module(BACKENDS_PACKAGE)
    except ModuleNotFoundError as e:
        print(f"[错误] 无法导入包 {BACKENDS_PACKAGE}: {e}")
        print("请确保 aicall/backends/__init__.py 存在")
        return backends

    for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{BACKENDS_PACKAGE}."):
        module_name = module_info.name
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"[警告] 导入模块 {module_name} 失败: {e}")
            traceback.print_exc()
            continue

        # 查找模块中定义的后端类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and issubclass(attr, AIBackend) and attr is not AIBackend):
                backend_name = getattr(attr, '__backend_name__', attr.__name__)
                supports_preheat = getattr(attr, '__supports_preheat__', False)
                backends.append({
                    "name": backend_name,
                    "module": module_name,
                    "class": attr_name,
                    "supports_preheat": supports_preheat
                })
                print(f"[发现后端] {backend_name} (模块: {module_name})")
                break  # 每个模块只取第一个后端类
    return backends

_backends_cache = None

def get_available_backends() -> List[Dict[str, Any]]:
    global _backends_cache
    if _backends_cache is None:
        _backends_cache = _discover_backends()
    return _backends_cache

def get_backend(backend_module: str, backend_class: str) -> AIBackend:
    module = importlib.import_module(backend_module)
    cls = getattr(module, backend_class)
    return cls()