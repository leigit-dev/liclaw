import requests
import json
from typing import Iterator, Dict, Any, List
from ..base import AIBackend


class LlamaServerBackend(AIBackend):
    """
    llama.cpp HTTP 服务器 (llama-server) 后端
    兼容 OpenAI Chat Completions API
    """
    __backend_name__ = "llama-server (本地)"
    __supports_preheat__ = False

    def __init__(self):
        # llama-server 默认地址
        self.base_url = "http://127.0.0.1:8080"
        self.model = "default"  # 单模型时任意字符串即可[reference:2]
        self.api_key = "no-key"  # llama-server 默认不验证 API Key[reference:3]

        # 默认生成参数
        self.default_max_tokens = 512
        self.default_temperature = 0.7
        self.default_top_p = 0.9
        self.default_top_k = 40

    def load(self, config: Dict[str, Any]) -> None:
        """
        加载配置，支持以下参数：
        - base_url: 服务器地址，默认 http://127.0.0.1:8080
        - model: 模型名称/路径[reference:4]
        - api_key: API 密钥（如服务器要求）
        - max_tokens, temperature, top_p, top_k: 采样参数
        """
        if 'base_url' in config:
            self.base_url = config['base_url'].rstrip('/')
        if 'model' in config:
            self.model = config['model']
        if 'api_key' in config:
            self.api_key = config['api_key']
        if 'max_tokens' in config:
            self.default_max_tokens = config['max_tokens']
        if 'temperature' in config:
            self.default_temperature = config['temperature']
        if 'top_p' in config:
            self.default_top_p = config['top_p']
        if 'top_k' in config:
            self.default_top_k = config['top_k']

        print(f"[*] llama-server 后端 - 地址: {self.base_url}, 模型: {self.model}")

    def stream_generate(
        self,
        messages: List[Dict[str, str]],
        enable_thinking: bool = False
    ) -> Iterator[Dict[str, str]]:
        """
        流式生成回复
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 构建 OpenAI 兼容的请求体[reference:5]
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.default_max_tokens,
            "temperature": self.default_temperature,
            "top_p": self.default_top_p,
            "top_k": self.default_top_k,
            "stream": True,
        }

        # llama.cpp 特有参数[reference:6]
        # Mirostat 采样（0=禁用，1=Mirostat 1.0，2=Mirostat 2.0）[reference:7]
        # payload["mirostat"] = 0
        # payload["mirostat_eta"] = 0.1
        # payload["mirostat_tau"] = 5.0

        # 思考模式：使用 deepseek 格式提取 reasoning_content[reference:8]
        if enable_thinking:
            payload["reasoning_format"] = "deepseek"

        url = f"{self.base_url}/v1/chat/completions"

        try:
            with requests.post(
                url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=120
            ) as resp:
                if resp.status_code != 200:
                    yield {
                        "type": "content",
                        "content": f"API错误 ({resp.status_code}): {resp.text}"
                    }
                    return

                for line in resp.iter_lines():
                    if not line:
                        continue

                    line = line.decode('utf-8').strip()
                    if not line.startswith('data: '):
                        continue

                    data = line[6:]
                    if data == '[DONE]':
                        break

                    try:
                        obj = json.loads(data)
                        choices = obj.get('choices', [])
                        if not choices:
                            continue

                        delta = choices[0].get('delta', {})

                        # 处理推理内容（思考模式）[reference:9]
                        if 'reasoning_content' in delta:
                            reasoning = delta['reasoning_content']
                            if reasoning and reasoning.strip():
                                yield {"type": "thinking", "content": reasoning}

                        # 处理普通内容
                        if 'content' in delta:
                            content = delta['content']
                            if content is not None and content.strip():
                                yield {"type": "content", "content": content}

                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.ConnectionError:
            yield {
                "type": "content",
                "content": "❌ 无法连接到 llama-server，请确保服务已启动（默认 http://127.0.0.1:8080）"
            }
        except requests.exceptions.Timeout:
            yield {"type": "content", "content": "❌ 请求超时，请检查服务器状态"}
        except Exception as e:
            yield {"type": "content", "content": f"请求异常: {str(e)}"}

    def unload(self) -> None:
        """释放资源（无需操作）"""
        pass