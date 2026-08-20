import os
import json
from typing import Generator, Dict, Any

tooltips = """
## 文件操作模块 (file)

- **file.read**：读取文件全部或部分行内容
  - args: {"path": "文件路径", "start_line": 起始行号（可选，从1开始）, "end_line": 结束行号（可选，不包含）}
  - 若未指定 start_line，则读取全部；若文件超过 1MB，则自动仅显示前 100 行。
  - 示例: <toolcall tool="file.read" args='{"path":"C:/test.txt"}'></toolcall>
  - 示例: <toolcall tool="file.read" args='{"path":"log.txt","start_line":10,"end_line":20}'></toolcall>

- **file.write**：写入文件（覆盖）
  - args: {"path": "文件路径"}
  - content: 要写入的文本内容（多行）
  - 示例: <toolcall tool="file.write" args='{"path":"out.txt"}' >Hello World</toolcall>

- **file.search**：在文件中搜索，返回目标行行号和内容
  - args: {"path": "文件路径", "pattern": "搜索字符串"}
  - 示例: <toolcall tool="file.search" args='{"path":"log.txt","pattern":"error"}'></toolcall>

- **file.replace**：替换文件指定行范围的内容
  - args: {"path": "文件路径", "start_line": 起始行（int）, "end_line": 终止行（int）}
  - content: 新内容
  - 示例: <toolcall tool="file.replace" args='{"path":"config.txt","start_line":5,"end_line":10}' >新配置</toolcall>
  - 注意：如果文件行数较多，请先用关键词查找起止位置的具体行号，再执行替换操作
"""

def execute(instruction: str, args: Dict[str, Any], content: str = "") -> Generator[str, None, None]:
    if instruction == "read":
        path = args.get("path")
        if not path:
            yield "错误：缺少 path 参数"
            return

        start_line = args.get("start_line")  # 可能为 None
        end_line = args.get("end_line")      # 可能为 None

        try:
            # 获取文件大小，用于判断是否过大
            file_size = os.path.getsize(path)
            MAX_SIZE = 1024 * 1024  # 1MB
            DEFAULT_LIMIT = 100     # 默认读取行数

            # 若未指定起始行且文件超大，只读取前 DEFAULT_LIMIT 行
            if start_line is None and file_size > MAX_SIZE:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= DEFAULT_LIMIT:
                            break
                        lines.append(line)
                    content_preview = '\n'.join(lines)
                    yield (f"文件过大（{file_size} 字节），仅显示前 {DEFAULT_LIMIT} 行。"
                           f"可使用 start_line 参数指定起始行。\n{content_preview}")
                return

            # 正常读取：全文件或部分行
            with open(path, 'r', encoding='utf-8') as f:
                if start_line is None:
                    # 读取全部
                    yield f.read()
                else:
                    # 读取指定行范围
                    lines = f.readlines()
                    total_lines = len(lines)
                    if start_line < 1:
                        start_line = 1
                    if end_line is None:
                        end_line = total_lines
                    elif end_line > total_lines:
                        end_line = total_lines

                    if start_line > total_lines:
                        yield f"起始行 {start_line} 超出文件总行数 {total_lines}"
                        return

                    if start_line > end_line:
                        yield f"起始行 {start_line} 大于结束行 {end_line}"
                        return

                    selected = lines[start_line-1:end_line]  # end_line 不包含，但用户期望包含该行，故切片正确
                    yield '\n'.join(selected)

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
            found = False
            with open(path, 'r', encoding='utf-8') as f:
                for line_no, line in enumerate(f, 1):
                    if pattern in line:
                        yield f"{line_no}: {line.rstrip()}"
                        found = True
            yield "搜索完成" + ("，没有找到内容" if not found else "")
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