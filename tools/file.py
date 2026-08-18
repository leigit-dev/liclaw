import os
import json
from typing import Generator, Dict, Any

tooltips = """
## 文件操作模块 (file)
- **file.read**：读取文件全部内容
  - args: {"path": "文件路径"}
  - 示例: <toolcall tool="file.read" args='{"path":"C:/test.txt"}'></toolcall>
- **file.write**：写入文件（覆盖）
  - args: {"path": "文件路径"}
  - content: 要写入的文本内容（多行）
  - 示例: <toolcall tool="file.write" args='{"path":"out.txt"}' >Hello World</toolcall>
- **file.search**：在文件中搜索模式
  - args: {"path": "文件路径", "pattern": "搜索字符串"}
  - 示例: <toolcall tool="file.search" args='{"path":"log.txt","pattern":"error"}'></toolcall>
- **file.replace**：替换文件指定行范围的内容
  - args: {"path": "文件路径", "start_line": 5, "end_line": 10}
  - content: 新内容
  - 示例: <toolcall tool="file.replace" args='{"path":"config.txt","start_line":5,"end_line":10}' >新配置</toolcall>
"""

def execute(instruction: str, args: Dict[str, Any], content: str = "") -> Generator[str, None, None]:
    if instruction == "read":
        path = args.get("path")
        if not path:
            yield "错误：缺少 path 参数"
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                yield f.read()
        except Exception as e:
            yield f"读取失败：{str(e)}"
    elif instruction == "write":
        path = args.get("path")
        if not path:
            yield "错误：缺少 path 参数"
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            yield f"文件 {path} 写入成功"
        except Exception as e:
            yield f"写入失败：{str(e)}"
    elif instruction == "search":
        path = args.get("path")
        pattern = args.get("pattern")
        if not path or not pattern:
            yield "错误：缺少 path 或 pattern 参数"
            return
        try:
            flag=1
            with open(path, 'r', encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if pattern in line:
                        yield f"{line_no}: {line.rstrip()}"
                        flag=0
            yield "搜索完成"+(",没有找到内容" if flag else none)
        except Exception as e:
            yield f"搜索失败：{str(e)}"
    elif instruction == "replace":
        path = args.get("path")
        start = args.get("start_line")
        end = args.get("end_line")
        if not path or start is None or end is None:
            yield "错误：缺少必要参数"
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            if start < 1 or end > len(lines) or start > end:
                yield f"无效行范围 {start}-{end}，文件共 {len(lines)} 行"
                return
            new_lines = lines[:start-1] + [content + '\n'] + lines[end:]
            with open(path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            yield f"替换行 {start}-{end} 成功"
        except Exception as e:
            yield f"替换失败：{str(e)}"
    else:
        yield f"未知指令 {instruction}"
