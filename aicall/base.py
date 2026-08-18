from abc import ABC, abstractmethod
from typing import Dict, Any, Iterator, Optional

class AIBackend(ABC):
    @abstractmethod
    def load(self, config: Dict[str, Any]) -> None:
        """加载模型或建立连接"""
        pass

    @abstractmethod
    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None,
                        max_tokens: int = 512, temperature: float = 0.7,
                        top_p: float = 0.9, enable_thinking: bool = False) -> Iterator[Dict[str, str]]:
        """
        流式生成回复
        每次 yield 一个字典，格式为：
        - {"type": "thinking", "content": "..."}  思考内容
        - {"type": "content", "content": "..."}   最终输出内容
        """
        pass

    @abstractmethod
    def unload(self) -> None:
        """释放资源"""
        pass

    @property
    def supports_preheat(self) -> bool:
        """是否需要预热（仅本地模型需要）"""
        return False

    def preheat(self) -> None:
        """预热模型（本地模型实现）"""
        pass