"""三阶段 Agent：采集 → 逐篇独立提取步骤 → 批量归纳模板"""
import asyncio
import json
import re
import sys
from pathlib import Path

# 确保 backend 目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from LLM.test_llm import LLMClient, LLMResponse
from tool.Tool_get_wechat import GetWechatTool

BACKEND_DIR = Path(__file__).resolve().parent.parent
ARTICLE_URL_DIR = BACKEND_DIR / "response" / "article_url"
TEMPLATE_DIR = ARTICLE_URL_DIR / "templates"


EXTRACT_SYSTEM_PROMPT = (
    "你是法律案例步骤抽取助手。你的任务是从给定文章中提取法律研判步骤序列。\n"
    "严格按以下JSON格式输出，不要输出任何其他内容：\n"
    '{"is_legal_case": bool, "is_relate": "high|mid|low", "steps": [...], "reason": "..."}\n'
    "字段说明：\n"
    "  is_legal_case: 文章是否包含法律案例分析（true/false）\n"
    "  is_relate: 文章内容与搜索关键词的匹配度\n"
    "  steps: 文章中实际出现的法律研判步骤序列（按先后顺序），非案例或无关时为空数组\n"
    "  reason: 简要判断依据\n"
    "注意：steps 只提取文章中实际出现的判断逻辑，不要预设或猜测步骤。"
)


class TestAgent1:
    """三阶段流程挖掘 Agent"""

    def __init__(self):
        self.llm = LLMClient()
        self.tools = {
            "search_wechat_articles": GetWechatTool(),
        }
        ARTICLE_URL_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    def _cached_url_path(self, keyword: str) -> Path:
        """返回关键词对应的缓存文件路径"""
        safe_name = re.sub(r"[^\w\-]", "_", keyword)
        return ARTICLE_URL_DIR / f"{safe_name}.json"

    async def _stage1_search(self, keyword: str) -> str | None:
        """阶段1：搜索公众号文章，优先从本地缓存读取，无缓存时才发起 tool calling"""
        cache_path = self._cached_url_path(keyword)

        # 检查缓存
        if cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8")
            print(f"\n>>> 阶段1：命中缓存，从本地读取: {cache_path}")
            return cached

        # 无缓存，发起搜索
        tool_schemas = [t.to_openai_schema() for t in self.tools.values()]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是法律案例流程挖掘助手。你的工作分三阶段："
                    "1) 搜索公众号文章 2) 逐篇提取研判步骤 3) 归纳流程模板。"
                    "严格按用户指令切换阶段。"
                ),
            },
            {
                "role": "user",
                "content": f"【阶段1】搜索微信公众号中与「{keyword}」相关的法律案例文章。直接调用工具，不要分析。",
            },
        ]

        print("\n>>> 阶段1：无缓存，发送搜索请求...")
        response = await self.llm.generate(messages, tools=tool_schemas)
        self._print_response(response)

        if not response.tool_calls:
            print("[WARN] LLM 未返回 tool_call")
            return None

        for tc in response.tool_calls:
            tool = self.tools.get(tc.function.name)
            if not tool:
                continue
            arguments = json.loads(tc.function.arguments)
            result = await tool.execute(arguments.get("query", keyword))
            if result.success:
                cache_path.write_text(result.content, encoding="utf-8")
                print(f"  已缓存至: {cache_path}")
                return result.content
            else:
                print(f"[ERROR] {result.error}")
                return None
        return None

    async def _stage2_extract(self, articles: list[dict], keyword: str) -> list[dict]:
        """阶段2：逐篇独立调用 LLM 提取步骤，每篇使用干净上下文"""
        results = []
        for i, article in enumerate(articles[:10]):
            title = article.get("title", "")
            summary = article.get("summary", "")
            article_text = f"标题：{title}\n摘要：{summary}"

            # 每次独立消息，不带历史，避免串扰
            msg = [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": f"关键词：{keyword}\n文章内容：{article_text}"},
            ]

            print(f"\n  [{i+1}/10] 提取: {title[:30]}...")
            resp = await self.llm.generate(msg)
            parsed = self._parse_extract_json(resp.content or "")
            if parsed:
                results.append(parsed)
            else:
                results.append({
                    "is_legal_case": False,
                    "is_relate": "low",
                    "steps": [],
                    "reason": f"解析失败: {resp.content[:100] if resp.content else '空响应'}",
                })
        return results

    async def _stage3_induce(self, step_results: list[dict], keyword: str) -> str:
        """阶段3：将所有有效步骤序列 + 已有模板一并交给 LLM 批量归纳"""
        valid = [r for r in step_results if r.get("is_legal_case")]
        if not valid:
            return "无有效案例，无法构建模板。"

        # 读取已有模板（如存在）
        existing_template = ""
        template_path = TEMPLATE_DIR / f"{re.sub(r'[^\w\-]', '_', keyword)}.json"
        if template_path.exists():
            existing_template = template_path.read_text(encoding="utf-8")

        step_sequences = json.dumps(
            [{"article": i+1, "steps": r["steps"], "reason": r.get("reason", "")}
             for i, r in enumerate(valid)],
            ensure_ascii=False,
        )

        # 构建归纳指令（不带 tool，先做文本输出验证）
        msg = [
            {
                "role": "system",
                "content": (
                    "你是法律流程模板归纳专家。你的任务是从多篇文章的步骤序列中，"
                    "归纳出通用的法律案件研判流程模板。"
                    "输出为JSON格式的模板结构，包含 nodes（步骤节点）和 edges（顺序关系/条件分支）。"
                    "如果提供了已有模板，请在其基础上合并新增的步骤和分支。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"【阶段3：归纳模板】\n"
                    f"关键词：{keyword}\n"
                    f"已有模板：\n{existing_template or '（无）'}\n"
                    f"本轮提取的步骤序列（共{len(valid)}篇有效案例）：\n{step_sequences}\n"
                    "请归纳为流程模板，输出为JSON：\n"
                    '{"crime_type": "...", "version": N, "nodes": [...], "edges": [...]}\n'
                    "nodes: [{id, type(检查/分支/结果), label, prompt(可选), frequency}]\n"
                    "edges: [{from, to, type(sequential/conditional), condition(可选)}]"
                ),
            },
        ]

        resp = await self.llm.generate(msg)
        template = resp.content or ""

        # 写入模板文件
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(template)
        print(f"\n  模板已写入: {template_path}")

        return template

    @staticmethod
    def _parse_extract_json(content: str) -> dict | None:
        """从 LLM 响应中提取 JSON 对象"""
        if not content:
            return None
        # 尝试匹配 ```json ... ``` 或直接 {...}
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
        else:
            m = re.search(r"(\{.*?\})", content, re.DOTALL)
            if m:
                content = m.group(1)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _print_response(resp: LLMResponse):
        if resp.thinking:
            print(f"  [思考] {resp.thinking[:150]}...")
        if resp.content:
            print(f"  [回复] {resp.content[:200]}")
        if resp.tool_calls:
            for tc in resp.tool_calls:
                print(f"  [工具调用] {tc.function.name}({tc.function.arguments})")

    async def run(self, keyword: str) -> str:
        print(f"=== 三阶段测试：关键词 = {keyword} ===")

        # ========== 阶段1：采集 ==========
        articles_json = await self._stage1_search(keyword)
        if not articles_json:
            return "阶段1失败：未获取到文章"

        articles = json.loads(articles_json)
        print(f"\n>>> 阶段1完成：共获取 {len(articles)} 篇轻量数据")

        # ========== 阶段2：逐篇独立提取步骤 ==========
        step_results = await self._stage2_extract(articles, keyword)
        legal_count = sum(1 for r in step_results if r.get("is_legal_case"))
        print(f"\n>>> 阶段2完成：有效案例 {legal_count}/{len(step_results)} 篇")

        # 保存中间结果供检查
        with open("stage2_step_results.json", "w", encoding="utf-8") as f:
            json.dump(step_results, f, ensure_ascii=False, indent=2)

        # ========== 阶段3：批量归纳模板 ==========
        template = await self._stage3_induce(step_results, keyword)
        print(f"\n>>> 阶段3完成：\n{template}")

        return template


if __name__ == "__main__":
    agent = TestAgent1()
    result = asyncio.run(agent.run("故意伤害案例判例"))
    print(f"\n=== 最终模板 ===\n{result}")
