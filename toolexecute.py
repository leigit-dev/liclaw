import importlib
import pkgutil
import json
from typing import Generator, Dict, Any, Optional

TOOLS_PACKAGE = "tools"

def discover_tools():
    tools = {}
    try:
        package = importlib.import_module(TOOLS_PACKAGE)
    except ModuleNotFoundError:
        print(f"警告：工具包 {TOOLS_PACKAGE} 未找到")
        return tools

    for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{TOOLS_PACKAGE}."):
        module_name = module_info.name
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, 'tooltips') and hasattr(module, 'execute'):
                short_name = module_name.split('.')[-1]
                tools[short_name] = {
                    'tooltips': module.tooltips,
                    'execute': module.execute
                }
                print(f"[工具] 加载模块 {short_name}")
        except Exception as e:
            print(f"[工具] 加载 {module_name} 失败: {e}")
    return tools

TOOLS = discover_tools()

def get_all_tooltips() -> str:
    """拼接所有模块的 tooltips 供 AI 使用"""
    parts = []
    for name, info in TOOLS.items():
        parts.append(info['tooltips'])
    return "\n".join(parts)

def execute_command_stream(command_obj: Dict[str, Any]) -> Generator[Dict[str, Any], None, None]:
    """
    执行命令并流式返回结果
    command_obj 格式: {"tool": "模块.指令", "argv": "参数字符串", "content": "内容"}
    """
    tool_full = command_obj.get("tool", "")
    if '.' not in tool_full:
        yield {"type": "error", "message": f"命令格式错误，应为 '模块.指令'，当前为 {tool_full}"}
        return

    module_name, instruction = tool_full.split('.', 1)
    if module_name not in TOOLS:
        yield {"type": "error", "message": f"未知模块 {module_name}"}
        return

    # 解析 args（JSON）
    args_str = command_obj.get("argv", "{}")
    try:
        args = json.loads(args_str) if args_str.strip() else {}
    except json.JSONDecodeError as e:
        yield {"type": "error", "message": f"args 解析失败：{str(e)}"}
        return

    content = command_obj.get("content", "")

    try:
        # 调用模块的 execute 生成器
        gen = TOOLS[module_name]['execute'](instruction, args, content)
        for chunk in gen:
            # chunk 可以是字符串或控制字典
            if isinstance(chunk, str):
                yield {"type": "output", "content": chunk}
            elif isinstance(chunk, dict):
                yield chunk
            else:
                yield {"type": "output", "content": str(chunk)}
    except Exception as e:
        yield {"type": "error", "message": f"执行异常：{str(e)}"}

    # 最后发送完成事件（前端可以据此结束）
    yield {"type": "done"}