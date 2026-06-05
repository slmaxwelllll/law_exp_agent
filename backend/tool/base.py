"""tool抽象基类，定义了tool的基本属性和方法，所有tool都需要继承自这个类"""
from typing import Any
from pydantic import BaseModel

class ToolResult(BaseModel):
    """工具执行结果"""
    success : bool
    content : str = ""
    error : str | None = None   

class Tool:
    """工具基类"""
    @property
    def name(self) -> str:
        """工具名称"""
        raise NotImplementedError
    @property
    def description(self) -> str:
        """工具描述"""
        raise NotImplementedError
    @property
    def parameters(self) -> dict[str, Any]:
        """工具参数"""
        raise NotImplementedError
    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore
        """执行方法"""
        raise NotImplementedError
    # 当前deepseek模型不支持Anthropic工具schema，所以不实现
    # def to_schema(self) -> dict[str, Any]:
    #     """将工具转换为Anthropic工具schema"""
    #     return {
    #         "name": self.name,
    #         "description": self.description,
    #         "input_schema": self.parameters,
    #     }
    def to_openai_schema(self) -> dict[str, Any]:
        """将工具转换为OpenAI工具schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }