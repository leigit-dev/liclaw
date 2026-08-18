import os

def read_file(path: str) -> str:
    """读取文件全部内容"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(path: str, content: str) -> str:
    """写入文件（覆盖）"""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def search_in_file(path: str, pattern: str) -> str:
    """在文件中搜索指定字符串，返回行号和内容"""
    try:
        results = []
        with open(path, 'r', encoding='utf-8') as f:
            for line_no, line in enumerate(f, 1):
                if pattern in line:
                    results.append(f"{line_no}: {line.rstrip()}")
        if results:
            return "\n".join(results)
        else:
            return f"Pattern '{pattern}' not found in {path}"
    except Exception as e:
        return f"Error searching file: {str(e)}"

def replace_in_range(path: str, start_line: int, end_line: int, new_content: str) -> str:
    """替换指定行范围内的内容（包含边界）"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return f"Invalid line range: {start_line}-{end_line}, file has {len(lines)} lines"
        # 替换行范围
        new_lines = lines[:start_line-1] + [new_content + '\n'] + lines[end_line:]
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return f"Replaced lines {start_line}-{end_line} in {path}"
    except Exception as e:
        return f"Error replacing in file: {str(e)}"

def execute_file_command(cmd: str) -> str:
    """解析并执行 file 命令"""
    parts = cmd.strip().split(maxsplit=3)
    if not parts:
        return "Empty file command"
    action = parts[0]
    if action == "file_read":
        if len(parts) < 2:
            return "Usage: file_read <path>"
        return read_file(parts[1])
    elif action == "file_write":
        if len(parts) < 3:
            return "Usage: file_write <path> <content>"
        return write_file(parts[1], parts[2])
    elif action == "file_search":
        if len(parts) < 3:
            return "Usage: file_search <path> <pattern>"
        return search_in_file(parts[1], parts[2])
    elif action == "file_replace":
        if len(parts) < 5:
            return "Usage: file_replace <path> <start_line> <end_line> <new_content>"
        try:
            start = int(parts[2])
            end = int(parts[3])
        except:
            return "Invalid line numbers"
        return replace_in_range(parts[1], start, end, parts[4])
    else:
        return f"Unknown file command: {action}"