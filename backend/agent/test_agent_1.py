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


from prompts import (
    STAGE_KW_DOMAIN_PROMPT,
    STAGE_2_A_SYSTEM_PROMPT,
    STAGE_2_B_SYSTEM_PROMPT,
    STAGE3_CLUSTER_PROMPT,
    STAGE3_INDUCE_PROMPT,
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

    async def _stage_kw_domain(self, keyword: str = "") -> dict:
        """阶段 kw：关键词 输出 法律制度定义（构成要件 + 法律效果）。一轮内复用，注入后续阶段。
        优先使用传入 keyword；为空时从 article_url 本地缓存文件名反推关键词。"""
        # 无关键词时，从本地 article_url 缓存提取
        if not keyword:
            cache_files = list(ARTICLE_URL_DIR.glob("*.json"))
            if cache_files:
                # 文件名格式：案例分析_公司合并.json → 案例分析 公司合并
                keyword = cache_files[0].stem.replace("_", " ")
                print(f"\n>>> stage_kw：从本地缓存提取关键词 [{keyword}]")
            else:
                return {"is_valid": False, "reason": "无关键词且无本地缓存文件"}

        msg = [
            {"role": "system", "content": STAGE_KW_DOMAIN_PROMPT},
            {"role": "user", "content": keyword},
        ]
        resp = await self.llm.generate(msg)
        legal_def = self._parse_extract_json(resp.content or "")
        if not legal_def or not legal_def.get("is_valid"):
            return {"is_valid": False, "reason": legal_def.get("reason", "关键词无法映射到法律制度") if legal_def else "stage_kw 解析失败"}
        print(f"\n>>> stage_kw：关键词 [{keyword}] 输出 领域 [{legal_def.get('domain')}]")
        return legal_def

    async def _stage2_process_one(self, article: dict, keyword: str, legal_def: dict, index: int, total: int) -> dict:
        """处理单篇文章：2A 结构分析 → 2B 提取研判步骤"""
        title = article.get("title", "")
        summary = article.get("summary", "")
        text = article.get("text", "")
        text_len = len(text)
        legal_def_json = json.dumps(legal_def, ensure_ascii=False)

        # --- 阶段2A：文章结构分析（头尾策略，覆盖开头概览和结尾分析）---
        if text_len > 4000:
            text_2a = text[:3000] + "\n===== 中间省略 =====\n" + text[-3000:]
        else:
            text_2a = text
        article_text_2a = f"标题：{title}\n摘要：{summary}\n正文：{text_2a}"

        print(f"\n  [{index+1}/{total}] 2A 结构分析: {title[:40]}...（原文{text_len}字）")
        msg_2a = [
            {"role": "system", "content": STAGE_2_A_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"【关键词法律制度定义】\n{legal_def_json}\n\n"
                f"关键词：{keyword}\n文章标题：{title}\n文章内容：{article_text_2a}"
            )},
        ]

        resp_2a = await self.llm.generate(msg_2a)
        sections_data = self._parse_extract_json(resp_2a.content or "")
        if not sections_data:
            return {
                "title": title,
                "is_case": False,
                "is_valid": False,
                "sections": [],
                "case_steps": [],
                "cross_steps": [],
                "reason": f"2A解析失败: {resp_2a.content[:100] if resp_2a.content else '空响应'}",
            }
        # 不在关键词制度框架内的文章直接跳过
        if not sections_data.get("is_valid", False):
            return {
                "title": title,
                "is_case": sections_data.get("is_case", False),
                "is_valid": False,
                "sections": sections_data.get("sections", []),
                "case_steps": [],
                "cross_steps": [],
                "reason": sections_data.get("reason", ""),
            }

        # 提取 article_issue 供 2B 使用
        article_issue = sections_data.get("article_issue", {})
        is_exceptional = article_issue.get("is_exceptional", False)
        cross_reference = article_issue.get("cross_reference", {})
        sections = sections_data.get("sections", [])

        # --- 阶段2B：基于结构提取研判步骤（给更多正文，最高 6000 字）---
        text_2b = text[:6000] if text_len > 6000 else text
        article_text_2b = f"标题：{title}\n摘要：{summary}\n正文：{text_2b}"

        print(f"  [{index+1}/{total}] 2B 步骤提取: {title[:40]}...")
        article_issue_json = json.dumps(article_issue, ensure_ascii=False)
        sections_json = json.dumps(sections_data, ensure_ascii=False)
        msg_2b = [
            {"role": "system", "content": STAGE_2_B_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"【关键词法律制度定义】\n{legal_def_json}\n\n"
                    f"【文章分析结果】\n{article_issue_json}\n\n"
                    f"关键词：{keyword}\n"
                    f"文章标题：{title}\n"
                    f"结构分析结果：\n{sections_json}\n"
                    f"文章原文：\n{article_text_2b}"
                ),
            },
        ]
        resp_2b = await self.llm.generate(msg_2b)
        steps_data = self._parse_extract_json(resp_2b.content or "")

        # 合并结果：is_valid 来自 2A（框架归入），case_steps/cross_steps 来自 2B
        case_steps = steps_data.get("case_steps", []) if steps_data else []
        cross_steps = steps_data.get("cross_steps", []) if steps_data else []

        return {
            "title": title,
            "is_case": sections_data.get("is_case", False),
            "is_valid": sections_data.get("is_valid", False),
            "is_exceptional": is_exceptional,
            "article_issue": article_issue,
            "keyword_framework": sections_data.get("keyword_framework", ""),
            "sections": sections,
            "topic": steps_data.get("topic", "") if steps_data else "",
            "conclusion": steps_data.get("conclusion", "") if steps_data else "",
            "case_steps": case_steps,
            "cross_steps": cross_steps,
            "reason": sections_data.get("reason", ""),
        }

    async def _stage2_extract(self, articles: list[dict], keyword: str, legal_def: dict) -> list[dict]:
        """阶段2：并发执行 10 篇 —— 2A 结构分析 → 2B 提取研判步骤"""
        articles = articles[:10]
        tasks = [
            self._stage2_process_one(article, keyword, legal_def, i, len(articles))
            for i, article in enumerate(articles)
        ]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _stage3_induce(self, step_results: list[dict], keyword: str, legal_def: dict) -> str:
        """阶段3：按核心主题聚类 → 聚类内归纳 → 输出模板树"""
        # 有效 case：is_valid=true 且（有标准步骤 或 有旁引步骤）
        valid = [r for r in step_results
                 if r.get("is_valid")
                 and (len(r.get("case_steps", [])) > 0 or len(r.get("cross_steps", [])) > 0)]
        if not valid:
            return "无有效案例，无法构建模板。", ""

        # 读取已有模板树
        existing_tree = ""
        template_path = TEMPLATE_DIR / f"{re.sub(r'[^\w\-]', '_', keyword)}.json"
        if template_path.exists():
            existing_tree = template_path.read_text(encoding="utf-8")

        # 从 stage2 结果中聚合所有 case
        case_data = []
        for i, r in enumerate(valid):
            case_data.append({
                "index": i + 1,
                "topic": r.get("topic", ""),
                "conclusion": r.get("conclusion", ""),
                "is_exceptional": r.get("is_exceptional", False),
                "case_steps": r.get("case_steps", []),
                "cross_steps": r.get("cross_steps", []),
                "cross_reference": r.get("article_issue", {}).get("cross_reference", {}),
                "sections": r.get("sections", []),
                "reason": r.get("reason", ""),
            })

        # --- 步骤1：LLM 按核心主题语义聚类 ---
        legal_def_json = json.dumps(legal_def, ensure_ascii=False)
        case_json = json.dumps(case_data, ensure_ascii=False)
        cluster_msg = [
            {"role": "system", "content": STAGE3_CLUSTER_PROMPT},
            {"role": "user", "content": (
                f"【关键词法律制度定义】\n{legal_def_json}\n\n"
                f"关键词：{keyword}\n案件列表：\n{case_json}"
            )},
        ]
        resp_cluster = await self.llm.generate(cluster_msg)
        cluster_data = self._parse_extract_json(resp_cluster.content or "")
        groups = cluster_data.get("groups", []) if cluster_data else []

        # 兜底：如果聚类失败，所有 case 归入一个默认组
        if not groups:
            groups = [{"label": keyword, "indices": [c["index"] for c in case_data]}]

        print(f"\n  Stage3 聚类结果：{len(groups)} 组 → {[g['label'] for g in groups]}")

        # --- 步骤2：每组内归纳子模板 ---
        index_to_case = {c["index"]: c for c in case_data}
        sub_templates = []

        for g in groups:
            group_cases = [index_to_case[idx] for idx in g["indices"] if idx in index_to_case]
            if not group_cases:
                continue

            group_json = json.dumps(group_cases, ensure_ascii=False)
            induce_msg = [
                {
                    "role": "system",
                    "content": STAGE3_INDUCE_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        f"【关键词法律制度定义】\n{legal_def_json}\n\n"
                        f"关键词：{keyword}\n"
                        f"本组标签：{g['label']}\n"
                        f"本组案例（共{len(group_cases)}篇）：\n{group_json}\n"
                        "请归纳为该主题的子流程模板，输出为JSON：\n"
                        '{"keyword": "...", "version": N, "nodes": [...], "edges": [...]}\n'
                        "nodes: [{id, type(关键词/主题/检查/分支/结果), label, prompt(可选), frequency}]\n"
                        "edges: [{from, to, type(sequential/conditional/未采纳), condition(可选)}]"
                    ),
                },
            ]
            resp = await self.llm.generate(induce_msg)
            sub_template = self._parse_extract_json(resp.content or "")
            if sub_template:
                sub_templates.append({
                    "label": g["label"],
                    "template": sub_template,
                })

        # --- 步骤3：跨聚类合并（简化为：完全相同 label 的合并）--- 暂不实现自动合并

        # --- 步骤4：组装模板树 ---
        template_tree = {
            "keyword": keyword,
            "version": 1,
            "sub_templates": sub_templates,
        }

        tree_json = json.dumps(template_tree, ensure_ascii=False, indent=2)
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(tree_json)
        return tree_json, str(template_path)

    @staticmethod
    def _parse_extract_json(content: str) -> dict | None:
        """从 LLM 响应中提取 JSON 对象"""
        if not content:
            return None
        # 尝试匹配 ```json ... ``` 或直接最外层 {...}（用贪婪匹配以处理嵌套对象）
        m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
        else:
            m = re.search(r"(\{.*\})", content, re.DOTALL)
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

        # ========== 阶段 kw：关键词 → 法律制度定义 ==========
        legal_def = await self._stage_kw_domain(keyword)
        if not legal_def.get("is_valid"):
            return f"阶段 kw 失败：{legal_def.get('reason')}"

        # ========== 阶段1：采集 ==========
        articles_json = await self._stage1_search(keyword)
        if not articles_json:
            return "阶段1失败：未获取到文章"

        articles = json.loads(articles_json)
        print(f"\n>>> 阶段1完成：共获取 {len(articles)} 篇轻量数据")

        # ========== 阶段2：逐篇独立提取步骤，返回步骤序列 ==========
        step_results = await self._stage2_extract(articles, keyword, legal_def)
        valid_count = sum(1 for r in step_results if r.get("is_valid"))
        exceptional_count = sum(1 for r in step_results if r.get("is_exceptional"))
        print(f"\n>>> 阶段2完成：有效 {valid_count}/{len(step_results)} 篇（其中例外 {exceptional_count} 篇）")

        # 保存中间结果供检查
        safe_name = re.sub(r"[^\w\-]", "_", keyword)
        stage2_path = STAGE2_RES_DIR / f"{safe_name}.json"
        stage2_path.write_text(json.dumps(step_results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  阶段2结果已写入: {stage2_path}")

        # # ========== 阶段3：批量归纳模板 ==========
        # template, template_path = await self._stage3_induce(step_results, keyword, legal_def)
        # # 渲染模板图
        # if template_path:
        #     try:
        #         visualize_service = VisualizeService()
        #         visualize_service.render_template_graph(template_path)
        #         print(f"\n  模板图已渲染")
        #     except Exception as e:
        #         print(f"渲染模板图失败: {e}")
        # print(f"\n>>> 阶段3完成：\n{template}")
        # return template
        return "阶段2完成。阶段3已截断。"


if __name__ == "__main__":
    agent = TestAgent1()
    result = asyncio.run(agent.run("案例分析 离婚诉讼"))
    print(f"\n=== 最终模板 ===\n{result}")
