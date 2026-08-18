"""
浏览器控制模块 - 基于 Playwright
全局单例浏览器实例，硬编码使用 Edge（msedge），headless 默认 False
前端不支持并行，因此全局单例是安全的。
"""
import json
import base64
import threading
import os
from typing import Generator, Dict, Any, Optional
from playwright.sync_api import sync_playwright, Browser, Page, ElementHandle

# ---------- 全局变量 ----------
_playwright = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None
_ref_map: Dict[str, ElementHandle] = {}
_global_lock = threading.Lock()
_headless = False  # 默认显示窗口
_channel = "msedge"  # 硬编码使用 Edge


# ---------- 浏览器生命周期 ----------
def _ensure_browser() -> Page:
    """确保浏览器和页面存在，返回 Page 对象"""
    global _playwright, _browser, _page, _ref_map

    with _global_lock:
        # 如果页面有效，直接返回
        if _page is not None:
            try:
                if not _page.is_closed():
                    return _page
            except Exception:
                pass

        # 关闭旧资源
        _close_browser()

        # 启动 Playwright
        _playwright = sync_playwright().start()

        # 尝试使用 msedge channel，如果失败则回退到系统 Edge 可执行文件
        try:
            _browser = _playwright.chromium.launch(channel=_channel, headless=_headless)
        except Exception as e:
            # 查找系统 Edge 路径
            edge_paths = [
                "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            ]
            edge_exe = None
            for p in edge_paths:
                if os.path.exists(p):
                    edge_exe = p
                    break
            if edge_exe:
                _browser = _playwright.chromium.launch(executable_path=edge_exe, headless=_headless)
            else:
                # 彻底失败，尝试默认 chromium（通常已安装）
                _browser = _playwright.chromium.launch(headless=_headless)

        _page = _browser.new_page()
        _ref_map.clear()
        return _page


def _close_browser():
    """关闭浏览器并释放资源"""
    global _playwright, _browser, _page, _ref_map
    if _page:
        try:
            _page.close()
        except Exception:
            pass
        _page = None
    if _browser:
        try:
            _browser.close()
        except Exception:
            pass
        _browser = None
    if _playwright:
        try:
            _playwright.stop()
        except Exception:
            pass
        _playwright = None
    _ref_map.clear()


# ---------- 元素引用管理 ----------
def _get_element_by_ref(ref: str) -> ElementHandle:
    if ref not in _ref_map:
        raise ValueError(f"元素引用 {ref} 不存在，请先执行 snapshot")
    return _ref_map[ref]


def _collect_interactive_elements(page: Page) -> Dict[str, str]:
    """收集可交互元素，返回 {ref: 描述}"""
    result = page.evaluate("""
        () => {
            function getXPath(element) {
                if (element.id) return '//*[@id="' + element.id + '"]';
                if (element === document.body) return '/html/body';
                let ix = 0;
                const siblings = element.parentNode.childNodes;
                for (let i = 0; i < siblings.length; i++) {
                    const sibling = siblings[i];
                    if (sibling === element) {
                        return getXPath(element.parentNode) + '/' + element.tagName.toLowerCase() + '[' + (ix + 1) + ']';
                    }
                    if (sibling.nodeType === 1 && sibling.tagName === element.tagName) ix++;
                }
                return '';
            }
            const elements = [];
            const selector = 'a, button, input, select, textarea, [role="button"], [role="link"], [contenteditable="true"]';
            document.querySelectorAll(selector).forEach((el, index) => {
                let desc = '';
                if (el.tagName === 'INPUT' && el.type) desc += el.type + ' ';
                if (el.tagName === 'A') desc += 'link ';
                if (el.tagName === 'BUTTON') desc += 'button ';
                const text = (el.innerText || el.value || el.placeholder || '').substring(0, 50);
                desc += text;
                const xpath = getXPath(el);
                if (!xpath) return;
                elements.push({
                    ref: '@e' + (index + 1),
                    xpath: xpath,
                    desc: desc.trim()
                });
            });
            return elements;
        }
    """)

    _ref_map.clear()
    desc_map = {}
    for item in result:
        ref = item['ref']
        xpath = item['xpath']
        desc = item['desc']
        desc_map[ref] = desc
        try:
            handle = page.locator(f"xpath={xpath}").element_handle
            if handle:
                _ref_map[ref] = handle
        except Exception:
            pass
    return desc_map


# ---------- 工具提示 ----------
tooltips = """
## 浏览器控制模块 (browser)
- **browser.open**：打开指定 URL（默认使用 Edge 浏览器，显示窗口）
  - args: {"url": "https://...", "headless": true}  （可选，若设为 true 则无头运行）
  - 示例: <toolcall tool="browser.open" args='{"url":"https://baidu.com"}'></toolcall>
  - 当且仅当用户要求不显示浏览器窗口时，可加 "headless": true

- **browser.snapshot**：获取页面可交互元素快照（交互式）
  - args: {"interactive_only": true} （默认 true）
  - 示例: <toolcall tool="browser.snapshot" args='{"interactive_only":true}'></toolcall>

- **browser.click**：点击元素（通过 ref）
  - args: {"ref": "@e1"}
  - 示例: <toolcall tool="browser.click" args='{"ref":"@e1"}'></toolcall>

- **browser.fill**：填写输入框
  - args: {"ref": "@e2", "text": "内容"}
  - 示例: <toolcall tool="browser.fill" args='{"ref":"@e2","text":"人工智能"}'></toolcall>

- **browser.get_text**：获取元素文本
  - args: {"ref": "@e3"}
  - 示例: <toolcall tool="browser.get_text" args='{"ref":"@e3"}'></toolcall>

- **browser.wait**：等待页面状态
  - args: {"state": "networkidle", "timeout": 30000}
  - 示例: <toolcall tool="browser.wait" args='{"state":"networkidle"}'></toolcall>

- **browser.close**：关闭浏览器
  - args: {}
  - 示例: <toolcall tool="browser.close" args='{}'></toolcall>

- **browser.go_back**、**browser.go_forward**、**browser.refresh**、**browser.screenshot** 等
  - 示例: <toolcall tool="browser.screenshot" args='{"path":"screenshot.png"}'></toolcall>
"""


# ---------- 主执行函数 ----------
def execute(instruction: str, args: Dict[str, Any], content: str = "") -> Generator[str, None, None]:
    """执行浏览器操作，流式返回结果"""
    global _headless

    try:
        # ----- 关闭浏览器 -----
        if instruction == "close":
            _close_browser()
            yield "浏览器已关闭"
            return

        # ----- 打开 URL -----
        if instruction == "open":
            url = args.get("url")
            if not url:
                yield "错误：缺少 url 参数"
                return
            # 更新 headless 设置（如果提供）
            if "headless" in args:
                _headless = args["headless"]
            else:
                _headless = False  # 默认显示窗口

            # 关闭旧浏览器，重新创建（应用新的 headless 设置）
            _close_browser()
            page = _ensure_browser()
            page.goto(url, wait_until="commit")
            _ref_map.clear()
            yield f"已打开 {url}（浏览器: {_channel}，headless={_headless}）"
            return

        # ----- 其他操作需要页面 -----
        page = _ensure_browser()
        if page is None:
            yield "错误：浏览器未启动，请先执行 open"
            return

        # ----- 快照 -----
        if instruction == "snapshot":
            interactive_only = args.get("interactive_only", True)
            if interactive_only:
                desc_map = _collect_interactive_elements(page)
                if not desc_map:
                    yield "未找到可交互元素"
                    return
                lines = ["可交互元素列表："]
                for ref, desc in desc_map.items():
                    lines.append(f"  {ref}: {desc}")
                yield "\n".join(lines)
            else:
                snapshot = page.accessibility.snapshot()
                if snapshot:
                    yield json.dumps(snapshot, indent=2, ensure_ascii=False)
                else:
                    yield "无法获取可访问性树"
            return

        # ----- 点击 -----
        if instruction == "click":
            ref = args.get("ref")
            if not ref:
                yield "错误：缺少 ref 参数"
                return
            try:
                elem = _get_element_by_ref(ref)
                elem.click()
                yield f"已点击 {ref}"
            except Exception as e:
                yield f"点击失败：{str(e)}"
            return

        # ----- 填写 -----
        if instruction == "fill":
            ref = args.get("ref")
            text = args.get("text", "")
            if not ref:
                yield "错误：缺少 ref 参数"
                return
            try:
                elem = _get_element_by_ref(ref)
                elem.fill(text)
                yield f"已填写 {ref} 内容为 {text}"
            except Exception as e:
                yield f"填写失败：{str(e)}"
            return

        # ----- 获取文本 -----
        if instruction == "get_text":
            ref = args.get("ref")
            if not ref:
                yield "错误：缺少 ref 参数"
                return
            try:
                elem = _get_element_by_ref(ref)
                text = elem.inner_text()
                yield f"{ref} 的文本：{text}"
            except Exception as e:
                yield f"获取文本失败：{str(e)}"
            return

        # ----- 等待 -----
        if instruction == "wait":
            state = args.get("state", "networkidle")
            timeout = args.get("timeout", 30000)
            try:
                page.wait_for_load_state(state, timeout=timeout)
                yield f"页面已等待至 {state}"
            except Exception as e:
                yield f"等待失败：{str(e)}"
            return

        # ----- 后退、前进、刷新、截图 -----
        if instruction == "go_back":
            try:
                page.go_back()
                yield "已后退"
            except Exception as e:
                yield f"后退失败：{str(e)}"
            return
        if instruction == "go_forward":
            try:
                page.go_forward()
                yield "已前进"
            except Exception as e:
                yield f"前进失败：{str(e)}"
            return
        if instruction == "refresh":
            try:
                page.reload()
                yield "已刷新"
            except Exception as e:
                yield f"刷新失败：{str(e)}"
            return
        if instruction == "screenshot":
            path = args.get("path")
            try:
                if path:
                    page.screenshot(path=path)
                    yield f"截图已保存至 {path}"
                else:
                    screenshot_bytes = page.screenshot()
                    b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    yield f"data:image/png;base64,{b64}"
            except Exception as e:
                yield f"截图失败：{str(e)}"
            return

        yield f"未知指令 {instruction}"

    except Exception as e:
        yield f"执行失败：{str(e)}"