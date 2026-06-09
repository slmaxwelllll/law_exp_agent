from typing import Any
from tool.base import Tool, ToolResult
from wechat_service.wechat_sougou import WechatSougouService
from wechat_service.data_parse import SougouMetaParseStrategy
from bs4 import BeautifulSoup
import json


class GetWechatTool(Tool):
    """获取微信文章工具"""
    @property
    def name(self) -> str:
        return "search_wechat_articles"
    @property
    def description(self) -> str:
        return "搜索微信公众号文章，返回与关键词相关的文章列表（含标题、摘要、正文、来源、日期）"
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，用于在微信公众号中搜索相关法律案例文章",
                },
            },
            "required": ["query"],
        }

    def __init__(self):
        self.wechat_crawler = WechatSougouService()
        self.meta_parser = SougouMetaParseStrategy()

    async def execute(self, keyword: str) -> ToolResult:
        """一次浏览器会话：搜索 → 逐篇跳转抓正文 → 解析合并（含全文 text 字段）"""
        try:
            search_html, article_details = await self.wechat_crawler.search_and_fetch_articles(keyword)
            meta_list = self.meta_parser.parse(search_html)

            # 将正文合并到元数据
            for i, meta in enumerate(meta_list):
                if i < len(article_details):
                    meta["text"] = self._extract_text(article_details[i].get("html", ""))
                else:
                    meta["text"] = ""

            return ToolResult(
                success=True,
                content=json.dumps(meta_list, ensure_ascii=False),
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    @staticmethod
    def _extract_text(html: str) -> str:
        """从 HTML 中提取纯文本"""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
