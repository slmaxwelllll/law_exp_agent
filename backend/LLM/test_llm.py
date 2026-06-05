from pathlib import Path
from openai import AsyncOpenAI
from dataclasses import dataclass

# 从 config/.env 读取 API Key
_env_path = Path(__file__).resolve().parent.parent / "config" / ".env"


def _load_api_key() -> str:
    """从 .env 文件读取 DEEPSEEK_API_KEY"""
    if _env_path.exists():
        for line in _env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"未找到 DEEPSEEK_API_KEY，请在 {_env_path} 中配置")


DEEPSEEK_API_KEY = _load_api_key()
@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list = None
    thinking: str = ""
    finish_reason: str = ""
    usage: object = None

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )

    async def generate(self, messages:list[dict], tools=None) -> LLMResponse:
        """生成请求-响应，接收消息列表，工具列表，返回LLM响应"""
        response = await self.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=messages,
            tools=tools or None
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=choice.message.tool_calls,
            finish_reason=choice.finish_reason,
            usage=response.usage,
        )
