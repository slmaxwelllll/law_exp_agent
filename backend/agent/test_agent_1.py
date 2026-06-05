"""管道1 最小测试：Agent 通过 Tool Calling 驱动微信搜索，获取轻量元数据"""
import asyncio
import json
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from LLM.test_llm import LLMClient, LLMResponse
from tool.Tool_get_wechat import GetWechatTool


class TestAgent1:
    """管道1 最小测试 Agent"""

    def __init__(self):
        self.llm = LLMClient()
        self.tools = {
            "search_wechat_articles": GetWechatTool(),
        }

    async def run(self, keyword: str) -> str:
        """主流程：发消息 → LLM 返回 tool_call → 执行 → 回传结果 → LLM 总结"""
        # 1. 准备 tool schema
        tool_schemas = [t.to_openai_schema() for t in self.tools.values()]

        # 2. 构建消息
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个法律案例信息采集助手。你的任务是根据用户提供的法律关键词，"
                    "调用工具搜索微信公众号文章，然后对搜索结果进行简要分析，如果可以最后返回一个针对法律关键词案件的。"
                    "当用户要求搜索时，请直接调用工具，不要先做解释。"
                ),
            },
            {
                "role": "user",
                "content": f"请搜索微信公众号中与「{keyword}」相关的法律案例文章。",
            },
        ]

        print(f"=== 管道1 测试：关键词 = {keyword} ===")

        # 3. 第一轮：发给 LLM，期望返回 tool_call
        print("\n>>> 第1轮：发送消息给 LLM...")
        response = await self.llm.generate(messages, tools=tool_schemas)
        self._print_response(response)

        # 如果没有 tool_call，说明 LLM 没理解意图，直接返回
        if not response.tool_calls:
            print("\n[WARN] LLM 未返回 tool_call，对话结束")
            return response.content or ""

        # 4. 执行 tool_call，把结果追加到 messages
        for tc in response.tool_calls:
            tool_name = tc.function.name
            arguments = json.loads(tc.function.arguments)
            keyword_arg = arguments.get("query", keyword)

            print(f"\n>>> 执行工具: {tool_name}(query={keyword_arg})")

            tool = self.tools.get(tool_name)
            if tool:
                result = await tool.execute(keyword_arg)
                tool_content = result.content if result.success else f"错误: {result.error}"
            else:
                tool_content = f"未知工具: {tool_name}"
            # 把第一步的result写入本地，检查轻量数据格式是否正确
            with open(f"test_{tc.id}.json", "w", encoding="utf-8") as f:
                f.write(tool_content)

            # 把 LLM 的 assistant 消息追加上去
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                ],
            })
            # 把 tool 执行结果追加上去
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_content,
            })

        # 5. 第二轮：把工具结果发给 LLM，拿最终分析
        print("\n>>> 第2轮：工具结果反馈给 LLM...")
        response = await self.llm.generate(messages, tools=tool_schemas)
        self._print_response(response)

        return response.content or ""

    @staticmethod
    def _print_response(resp: LLMResponse):
        """打印 LLM 响应的关键信息"""
        if resp.thinking:
            print(f"[思考] {resp.thinking[:200]}...")
        if resp.content:
            print(f"[回复] {resp.content[:300]}")
        if resp.tool_calls:
            for tc in resp.tool_calls:
                print(f"[工具调用] {tc.function.name}({tc.function.arguments})")


if __name__ == "__main__":
    # 硬编码测试关键词
    agent = TestAgent1()
    result = asyncio.run(agent.run("酒驾肇事逃逸"))
    print(f"\n=== 最终结果 ===\n{result}")
