import subprocess
import json
from typing import Generator, Dict, Any

tooltips = """
## 系统命令模块 (system)
- **system.exec**：执行任意系统命令
  - args: {"cmd": "具体命令", "timeout": 60, "encoding": "utf-8"}
  - 示例: <toolcall tool="system.exec" args='{"cmd":"dir C:/","timeout":30}'></toolcall>
- **system.cd**：切换当前工作目录
  - args: {"path": "目标路径"}
  - 示例: <toolcall tool="system.cd" args='{"path":"D:/project"}'></toolcall>
"""

def execute(instruction: str, args: Dict[str, Any], content: str = "") -> Generator[str, None, None]:
    if instruction == "exec":
        cmd = args.get("cmd")
        if not cmd:
            yield "错误：缺少 cmd 参数"
            return
        timeout = args.get("timeout", 60)
        encoding = args.get("encoding", "gbk")
        try:
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding=encoding, errors='replace')
            # 实时读取输出（可能阻塞，但可逐行读）
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if line:
                    yield line.rstrip()
            # 读取剩余 stderr
            stderr = proc.stderr.read()
            if stderr:
                yield "[stderr] " + stderr.strip()
            if proc.returncode != 0:
                yield f"命令返回码 {proc.returncode}"
            else:
                yield "命令执行完成"
        except subprocess.TimeoutExpired:
            proc.kill()
            yield f"命令执行超时（>{timeout}秒）"
        except Exception as e:
            yield f"执行出错：{str(e)}"
    elif instruction == "cd":
        path = args.get("path")
        if not path:
            yield "错误：缺少 path 参数"
            return
        try:
            os.chdir(path)
            yield f"当前目录切换至 {os.getcwd()}"
        except Exception as e:
            yield f"切换目录失败：{str(e)}"
    elif instruction == "ping":
        host = args.get("host")
        count = args.get("count", 4)
        if not host:
            yield "错误：缺少 host 参数"
            return
        # 简单实现，也可用 system.exec 替代，但单独提供便于识别
        cmd = f"ping -n {count} {host}"
        for out in execute("exec", {"cmd": cmd}, content=""):
            yield out
    else:
        yield f"未知指令 {instruction}"
