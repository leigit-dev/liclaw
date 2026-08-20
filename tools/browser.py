"""
浏览器控制模块 - 基于 Playwright
全局单例，硬编码使用 msedge，headless 默认 False
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
_headless = False
_channel = "msedge"


def _ensure_browser() -> Page:
    """确保浏览器已启动并返回当前页面（旧页面或新页面，由调用者决定）"""
    global _playwright, _browser, _page, _ref_map
    with _global_lock:
        if _page is not None:
            try:
                if not _page.is_closed():
                    return _page
            except Exception:
                pass
        _close_browser()
        _playwright = sync_playwright().start()
        try:
            _browser = _playwright.chromium.launch(channel=_channel, headless=_headless)
        except Exception:
            # 回退到系统 Edge
            edge_paths = [
                "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
                "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
            ]
            edge_exe = next((p for p in edge_paths if os.path.exists(p)), None)
            if edge_exe:
                _browser = _playwright.chromium.launch(executable_path=edge_exe, headless=_headless)
            else:
                _browser = _playwright.chromium.launch(headless=_headless)
        _page = _browser.new_page()
        _ref_map.clear()
        return _page


def _close_browser():
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


def _get_current_page() -> Page:
    """
    获取当前浏览器的最新活动页面（自动处理新标签页）。
    注意：此函数仅用于需要主动切换页面时调用，不应在每次操作前无条件调用，
    否则可能因对象比较问题导致 _ref_map 被误清空。
    """
    global _browser, _page, _ref_map
    if _browser is None:
        raise RuntimeError("浏览器未启动")
    pages = _browser.contexts[0].pages if _browser.contexts else []
    if not pages:
        return _ensure_browser()
    current = pages[-1]

    # 仅在 _page 为空、已关闭或 URL 发生实际变化时才更新
    if _page is None or _page.is_closed():
        _page = current
        _ref_map.clear()
    elif current.url != _page.url:
        _page = current
        _ref_map.clear()
    return _page


def _get_element_by_ref(ref: str) -> ElementHandle:
    if ref not in _ref_map:
        raise ValueError(f"元素引用 {ref} 不存在，请先执行 snapshot")
    return _ref_map[ref]


def _collect_interactive_elements(page: Page) -> Dict[str, str]:
    """收集页面可交互元素，返回 ref -> 描述 的字典，并更新 _ref_map"""
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
            handle = page.locator(f"xpath={xpath}").element_handle()
            if handle:
                _ref_map[ref] = handle
        except Exception:
            pass
    return desc_map


tooltips = """
## 浏览器控制模块 (browser)
- **browser.open**：打开 URL
  - args: {"url": "https://...", "headless": false}
  - 示例: <toolcall tool="browser.open" args='{"url":"https://www.qq.com"}'></toolcall>

- **browser.snapshot**：获取可交互元素列表（分配 @eN 引用）
  - args: {"interactive_only": true}
  - 示例: <toolcall tool="browser.snapshot" args='{"interactive_only":true}'></toolcall>

- **browser.click**：点击元素（通过 @eN）
  - args: {"ref": "@e1"}
  - 示例: <toolcall tool="browser.click" args='{"ref":"@e5"}'></toolcall>

- **browser.fill**：填写输入框
  - args: {"ref": "@e2", "text": "内容"}
  - 示例: <toolcall tool="browser.fill" args='{"ref":"@e2","text":"人工智能"}'></toolcall>

- **browser.get_text**：获取元素文本
  - args: {"ref": "@e3"}
  - 示例: <toolcall tool="browser.get_text" args='{"ref":"@e10"}'></toolcall>

- **browser.wait**：等待页面加载
  - args: {"state": "networkidle", "timeout": 30000}
  - 示例: <toolcall tool="browser.wait" args='{"state":"networkidle"}'></toolcall>

- **browser.close**：关闭浏览器
  - args: {}
  - 示例: <toolcall tool="browser.close" args='{}'></toolcall>

- **browser.go_back**：后退一页
  - args: {}
  - 示例: <toolcall tool="browser.go_back" args='{}'></toolcall>

- **browser.go_forward**：前进一页
  - args: {}
  - 示例: <toolcall tool="browser.go_forward" args='{}'></toolcall>

- **browser.refresh**：刷新当前页面
  - args: {}
  - 示例: <toolcall tool="browser.refresh" args='{}'></toolcall>

- **browser.screenshot**：截图（保存文件或返回 base64）
  - args: {"path": "screenshot.png"}（可选）
  - 示例: <toolcall tool="browser.screenshot" args='{"path":"page.png"}'></toolcall>

需要注意的是，当刷新、后退、前进、点击元素、填写输入框等操作后，页面可能会发生变化，之前分配的 @eN 引用可能失效。在每次操作后需要重新执行 snapshot 以获取最新的可交互元素列表。
"""


def execute(instruction: str, args: Dict[str, Any], content: str = "") -> Generator[str, None, None]:
    global _headless, _page, _ref_map
    try:
        if instruction == "close":
            _close_browser()
            yield "浏览器已关闭"
            return

        if instruction == "open":
            url = args.get("url")
            if not url:
                yield "错误：缺少 url 参数"
                return
            _headless = args.get("headless", False)
            _close_browser()
            page = _ensure_browser()
            page.goto(url, wait_until="commit")
            _ref_map.clear()
            yield f"已打开 {url}（浏览器: {_channel}，headless={_headless}）"
            return

        # 对于除 open/close 外的所有操作，确保浏览器已启动并获取当前页面
        page = _ensure_browser()
        if page is None:
            yield "错误：浏览器未启动，请先执行 open"
            return

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
                yield json.dumps(snapshot, indent=2, ensure_ascii=False) if snapshot else "无法获取可访问性树"
            return

        if instruction == "click":
            ref = args.get("ref")
            if not ref:
                yield "错误：缺少 ref 参数"
                return
            try:
                elem = _get_element_by_ref(ref)
                # 点击前记录页面数量和当前 URL
                pages_before = _browser.contexts[0].pages if _browser.contexts else []
                url_before = page.url

                elem.click()

                # 检测是否有新标签页打开
                pages_after = _browser.contexts[0].pages if _browser.contexts else []
                if len(pages_after) > len(pages_before):
                    # 新标签页已打开，切换到最新页面
                    _page = pages_after[-1]
                    _ref_map.clear()
                    # 等待新页面加载完成（可选）
                    try:
                        _page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    yield f"已点击 {ref}，检测到新标签页并已切换。请重新执行 snapshot 获取新页面元素。"
                else:
                    # 没有新标签页，但可能发生了页面内导航
                    # 点击后不立即清空引用，但可以提示用户如页面变化需重新 snapshot
                    # 为避免误清空，这里不自动清空，除非 URL 发生变化
                    # 我们可以在下一次 snapshot 时自动检测（snapshot 内部会重建引用）
                    yield f"已点击 {ref}。如果页面内容发生变化，请重新执行 snapshot。"
            except Exception as e:
                yield f"点击失败：{str(e)}"
            return

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

        if instruction == "wait":
            state = args.get("state", "networkidle")
            timeout = args.get("timeout", 30000)
            try:
                page.wait_for_load_state(state, timeout=timeout)
                yield f"页面已等待至 {state}"
            except Exception as e:
                yield f"等待失败：{str(e)}"
            return

        if instruction == "go_back":
            try:
                page.go_back()
                yield "已后退，请重新执行 snapshot 获取新元素"
            except Exception as e:
                yield f"后退失败：{str(e)}"
            return

        if instruction == "go_forward":
            try:
                page.go_forward()
                yield "已前进，请重新执行 snapshot 获取新元素"
            except Exception as e:
                yield f"前进失败：{str(e)}"
            return

        if instruction == "refresh":
            try:
                page.reload()
                yield "已刷新，请重新执行 snapshot 获取新元素"
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
                    b64 = base64.b64encode(page.screenshot()).decode('utf-8')
                    yield f"data:image/png;base64,{b64}"
            except Exception as e:
                yield f"截图失败：{str(e)}"
            return

        yield f"未知指令 {instruction}"

    except Exception as e:
        yield f"执行失败：{str(e)}"