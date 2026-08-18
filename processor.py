import os
import json
import re
import time
import queue
import threading
import psutil,platform
from typing import Optional, Tuple, Dict, Any, Generator, List

# 从 aicall 导入后端管理
from aicall.factory import get_available_backends, get_backend
from aicall.base import AIBackend

# 导入工具提示词生成（从 toolexecute 获得）
from toolexecute import get_all_tooltips

# ---------- 构建动态系统提示 ----------
def build_ai_tips() -> str:
    base = f"""你是一个自主执行助手。你需要将用户的指令拆解为一系列命令行操作，使用以下统一格式输出：

<toolcall tool="模块名.指令名" args="JSON参数">可选的长文本内容</toolcall>
其中，args为json风格，但不识别任何“\\”转义字符。JSON不得换行。输出“\\\\”将被识别为两个“\\”字符。长文本部分允许换行。

**重要**：每次可以输出多个 `<toolcall>`，系统会按顺序执行。当所有任务完成，并且所有调用的工具都返回恰当的结果时，输出 `<-----FINISH----->`，然后输出对本次任务的总结。
如果执行了工具，请不要在第一次对话中就输出<-----FINISH----->，必须等待看到结果确认后才可以完成任务。

当前系统的信息:{platform.system()},{platform.platform()},{platform.architecture()}

以下是所有可用的工具模块及其指令说明：

"""
    base += get_all_tooltips()
    return base

AITIPS = build_ai_tips()

# ---------- 全局后端状态 ----------
_backend = None
_backend_info = None
_available_backends = get_available_backends()

# ---------- 会话存储路径 ----------
CHAT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chat')
os.makedirs(CHAT_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
agent_queues: Dict[str, queue.Queue] = {}

# ---------- 后端加载函数 ----------
def load_backend(backend_name: str, verbose=True):
    global _backend, _backend_info
    for b in _available_backends:
        if b['name'] == backend_name:
            backend_info = b
            break
    else:
        raise ValueError(f"未知后端: {backend_name}")
    if _backend:
        _backend.unload()
    _backend = get_backend(backend_info['module'], backend_info['class'])
    _backend.load({})
    _backend_info = backend_info
    if verbose:
        print(f"[+] 后端 {backend_name} 加载完成")

def get_current_backend_info():
    return _backend_info

def preheat_backend():
    if _backend and _backend.supports_preheat:
        _backend.preheat()

def get_available_backends():
    return _available_backends

# ---------- AI 流式调用 ----------
def stream_ask(messages: List[Dict[str, str]], enable_thinking: bool = False) -> Generator[Dict[str, str], None, None]:
    if _backend is None:
        raise RuntimeError("后端未加载")
    yield from _backend.stream_generate(messages, enable_thinking)

# ---------- 会话管理函数 ----------
def save_conversation(session_id: str, messages: List[Dict]):
    path = os.path.join(CHAT_DIR, f"{session_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def load_conversation(session_id: str) -> List[Dict]:
    path = os.path.join(CHAT_DIR, f"{session_id}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def list_sessions() -> List[Dict]:
    sessions = []
    for fname in os.listdir(CHAT_DIR):
        if fname.endswith('.json'):
            session_id = fname[:-5]
            path = os.path.join(CHAT_DIR, fname)
            with open(path, 'r', encoding='utf-8') as f:
                msgs = json.load(f)
            title = msgs[0]['content'][:30] if msgs else session_id
            sessions.append({'id': session_id, 'title': title, 'updated': os.path.getmtime(path)})
    sessions.sort(key=lambda x: x['updated'], reverse=True)
    return sessions

def delete_session(session_id: str):
    path = os.path.join(CHAT_DIR, f"{session_id}.json")
    if os.path.exists(path):
        os.remove(path)

def get_system_status():
    return {
        'ai_loaded': _backend is not None,
        'backend_type': _backend_info['name'] if _backend_info else '未加载',
        'cpu_percent': psutil.cpu_percent(interval=0.5),
        'memory_mb': round(psutil.Process().memory_info().rss / 1024 / 1024, 1)
    }

# ---------- TaskAgent 类 ----------
class TaskAgent:
    def __init__(self, task: str, session_id: str):
        self.session_id = session_id
        self.messages = load_conversation(session_id)
        if not self.messages:
            self.messages = [{"role": "user", "content": task}]
        else:
            self.messages.append({"role": "user", "content": task})
        save_conversation(session_id, self.messages)
        self._stop = False
        self._start_time = time.time()
        self._waiting_approval = False

    def receive_input(self, user_msg: str):
        self.messages.append({"role": "user", "content": user_msg})
        save_conversation(self.session_id, self.messages)

    def stop(self):
        self._stop = True

    def add_command_result(self, command: str, success: bool, output: str):
        """前端执行命令后调用此方法将结果加入对话"""
        result_msg = f"执行命令: {command}\n结果: {'成功' if success else '失败'}\n输出: {output[:500]}"
        self.messages.append({"role": "assistant", "content": result_msg})
        save_conversation(self.session_id, self.messages)

    def generate_next_command(self, enable_thinking: bool = False) -> Generator[Dict, None, None]:
        messages = [{"role": "system", "content": AITIPS}] + self.messages
        messages.append({"role": "user", "content": "请输出下一步需要执行的命令（使用 <toolcall> 格式）或 <-----FINISH----->并总结。"})

        full_response = ""
        for chunk in stream_ask(messages, enable_thinking=enable_thinking):
            #print(chunk)
            if chunk['type'] == 'thinking':
                yield {'type': 'thinking', 'content': chunk['content']}
            else:
                full_response += chunk['content']
                yield {'type': 'partial', 'content': chunk['content']}
        print(full_response)
        commands = self._parse_commands(full_response)

        print(commands)
        if commands and len(commands) > 0:
            for cmd in commands:
                yield {'type': 'command', 'command': cmd}
        else:
            yield {'type': 'command', 'command': None}   # 或根据 finish 判断

    def _parse_commands(self, text: str) -> List[Dict]:
        # 匹配 args="..." 或 args='...'
        pattern = re.compile(
            r'<toolcall\s+tool=(?:["\'])([^"\']*?)(?:["\'])(?:\s+args=(["\'])((?:[^\\]|\\.)*?)\2)?\s*>(.*?)</toolcall>',
            re.DOTALL
        )
        commands = []
        for match in pattern.finditer(text):
            tool = match.group(1)
            # 如果 args 匹配到，group(3) 是引号内的内容；否则默认 "{}"
            if match.group(2):
                args_str = match.group(3)  # 引号内的内容
            else:
                args_str = "{}"
            content = match.group(4).strip() if match.group(4) else ""
            commands.append({'tool': tool, 'argv': args_str, 'content': content})
        return commands

    def generate_summary(self) -> Generator[str, None, None]:
        """生成最终总结（流式）"""
        messages = [{"role": "system", "content": "你是一个智能助手，简洁汇报。"}] + self.messages
        messages.append({"role": "user", "content": "请用自然语言向用户汇报任务完成情况。"})
        for chunk in stream_ask(messages, enable_thinking=False):
            if chunk['type'] == 'content':
                yield chunk['content']