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
from wechat_service.visualize import VisualizeService

BACKEND_DIR = Path(__file__).resolve().parent.parent
RESPONSE_DIR = BACKEND_DIR / "response"
ARTICLE_URL_DIR = RESPONSE_DIR / "article_url"       # 阶段1：搜索缓存
STAGE2_RES_DIR = RESPONSE_DIR / "stage2_res"          # 阶段2：步骤提取中间结果
TEMPLATE_DIR = RESPONSE_DIR / "templates"             # 阶段3：流程模板


STAGE_2_A_SYSTEM_PROMPT = (
    "你是法律文章结构分析助手。你的任务是先理解文章的整体结构，再标注每部分的类型和用途。\n"
    "法律文章通常由以下类型的段落混合组成：\n"
    "  - 法条引述：原文引用或转述法律条文，提供规范依据\n"
    "  - 裁判规则论述：抽象层面的法律适用规则或司法解释\n"
    "  - 争议焦点：列出该案存在的法律分歧点或争议问题\n"
    "  - 案例事实：具体案件的案情描述（当事人、时间线、行为等）\n"
    "  - 案例研判：对具体案件的法律推理、观点比较、裁判逻辑\n"
    "  - 法理评析：对裁判背后法理的延伸讨论（如法官后语、学者点评）\n"
    "  - 程序说明：诉讼程序性描述（起诉、送达、开庭等）\n"
    "  - 其他：不属于以上类型的内容\n"
    "\n"
    "严格按以下JSON格式输出，不要输出任何其他内容：\n"
    '{\n'
    '  "is_legal_case": bool,\n'
    '  "is_relate": "high|mid|low",\n'
    '  "sections": [\n'
    '    {\n'
    '      "seq": 序号(从1开始),\n'
    '      "type": "段落类型",\n'
    '      "summary": "这部分核心内容的一句话概括",\n'
    '      "purpose": "提供框架 | 展示研判方法 | 说明背景 | 无直接价值"\n'
    '    }\n'
    '  ],\n'
    '  "reason": "整体判断依据"\n'
    '}\n'
    "重要规则：\n"
    "  - sections 按原文出现顺序排列，seq 递增\n"
    "  - summary 必须具体（不能只写\"法条内容\"，要说清楚是哪个法条、讲什么）\n"
    "  - purpose 必须明确该段落对后续步骤提取的作用\n"
    "  - 即使文章包含多个段落类型，也必须逐一列出"
)

STAGE_2_B_SYSTEM_PROMPT = (
    "你是法律研判步骤提取助手。你将收到一篇文章的结构分析（sections）和原文正文。\n"
    "你的任务是从文章的「案例研判」「争议焦点」「法理评析」等段落中提取法律研判步骤。\n"
    "\n"
    "★★★ 核心法则：法律关系的客体层级 ★★★\n"
    "任何法律案件的审理都遵循天然的客体依赖层级。你必须按此层级组织步骤：\n"
    "\n"
    "  主客体（Primary Object）：\n"
    "    案件的核心法律关系本身。必须先判断主客体是否成立。\n"
    '    判断方法：问自己"如果这一步不成立，案件是否直接被驳回或判败诉？"\n'
    "    若是 → 主客体；若否 → 从客体。\n"
    '    简言之：案件"能不能赢"依赖主客体，"赢多少/怎么处理"依赖从客体。\n'
    "\n"
    "  从客体（Secondary Object）：\n"
    "    依附于主客体成立后才处理的后果性客体。\n"
    "    只有当主客体已判断为成立，才进入从客体的分析。\n"
    "    各从客体之间是并列关系，无先后依赖。\n"
    "\n"
    "★★★ 提取规则 ★★★\n"
    "1. 步骤仅从「案例研判」「争议焦点」「法理评析」段落提取，不从「法条引述」直接生成步骤\n"
    '2. 每个步骤标注其所属客体类型："主客体" 或 "从客体"\n'
    "3. 同一案件内，主客体步骤全部排在前，从客体步骤排在后面\n"
    '4. 法条引述中的列举项（如"14种情形"）不得拆散为独立步骤，应作为判断依据合并到主客体步骤中\n'
    "5. 诉讼法上的程序性节点（起诉、送达、开庭、上诉）不作为研判步骤，除非该程序本身是争议焦点\n"
    "6. 判决不准离婚后再次起诉属于第二次独立诉讼，不建模为流程回边\n"
    "\n"
    "严格按以下JSON格式输出，不要输出任何其他内容：\n"
    '{\n'
    '  "case_steps": [\n'
    '    {\n'
    '      "case_label": "案例名称或简短标识",\n'
    '      "section_seq": 来源段落的seq号,\n'
    '      "steps": [\n'
    '        {\n'
    '          "seq": 步骤序号(从1开始),\n'
    '          "object_type": "主客体 | 从客体",\n'
    '          "step": "具体的研判动作描述"\n'
    '        }\n'
    '      ]\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "注意：\n"
    "  - 如果原文只有法条框架而无具体案例，case_steps 可为空数组\n"
    '  - 步骤描述必须是具体的研判动作（如"对比两种意见，采纳第二种"），不能是抽象法条复述\n'
    "  - 多个案例的步骤分别放在不同的 case_steps 条目中"
)

class TestAgent1:
    """三阶段流程挖掘 Agent"""

    def __init__(self):
        self.llm = LLMClient()
        self.tools = {
            "search_wechat_articles": GetWechatTool(),
        }
        ARTICLE_URL_DIR.mkdir(parents=True, exist_ok=True)
        STAGE2_RES_DIR.mkdir(parents=True, exist_ok=True)
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
            text = article.get("text", "")
            # 截断正文到 3000 字，控制 token 消耗
            article_text = f"标题：{title}\n摘要：{summary}\n正文：{text[:3000]}"

            msg = [
                {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                {"role": "user", "content": f"关键词：{keyword}\n文章内容：{article_text}"},
            ]

            print(f"\n  [{i+1}/10] 提取: {title[:30]}...（正文{len(text)}字）")
            resp = await self.llm.generate(msg)
            parsed = self._parse_extract_json(resp.content or "")
            if parsed:
                results.append(parsed)
            else:
                results.append({
                    "is_legal_case": False,
                    "is_relate": "low",
                    "steps": [],
                    "text": text[:200],
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
        return template, str(template_path)

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

        # ========== 阶段2：逐篇独立提取步骤，返回步骤序列 ==========
        step_results = await self._stage2_extract(articles, keyword)
        legal_count = sum(1 for r in step_results if r.get("is_legal_case"))
        print(f"\n>>> 阶段2完成：有效案例 {legal_count}/{len(step_results)} 篇")

        # 保存中间结果供检查
        safe_name = re.sub(r"[^\w\-]", "_", keyword)
        stage2_path = STAGE2_RES_DIR / f"{safe_name}.json"
        stage2_path.write_text(json.dumps(step_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  阶段2结果已写入: {stage2_path}")

        # ========== 阶段3：批量归纳模板 ==========
        template, template_path = await self._stage3_induce(step_results, keyword)
        # 渲染模板图
        try:
            visualize_service = VisualizeService()
            visualize_service.render_template_graph(template_path)
            print(f"\n  模板图已渲染")
        except Exception as e:
            print(f"渲染模板图失败: {e}")
        print(f"\n>>> 阶段3完成：\n{template}")
        return template


if __name__ == "__main__":
    agent = TestAgent1()
    result = asyncio.run(agent.run("案例分析 离婚诉讼"))
    print(f"\n=== 最终模板 ===\n{result}")
