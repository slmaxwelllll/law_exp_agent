from typing import Any
from tool.base import Tool, ToolResult
from wechat_service.wechat_sougou import WechatSougouService
from wechat_service.data_parse import HtmlParseStrategy, SougouMetaParseStrategy
import json


class GetWechatTool(Tool):
    """获取微信文章工具"""
    @property
    def name(self) -> str:
        return "search_wechat_articles"
    @property
    def description(self) -> str:
        return "搜索微信公众号文章，返回与关键词相关的文章列表（含标题、摘要、来源、日期）"
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
        self.url_parser = HtmlParseStrategy()          # 管道2: 提取URL列表
        self.meta_parser = SougouMetaParseStrategy()   # 管道1: 提取轻量元数据

    async def execute(self, keyword: str) -> ToolResult:
        """管道1: 搜索并返回轻量元数据，反馈给 LLM 决策"""
        try:
            html_content = await self.wechat_crawler.search_by_keyword(keyword)
            meta_list = self.meta_parser.parse(html_content)
            return ToolResult(
                success=True,
                content=json.dumps(meta_list, ensure_ascii=False),
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def fetch_article_details(self, keyword: str) -> list[dict]:
        """管道2: 完整抓取文章正文，进入模板构造链路"""
        html_content = await self.wechat_crawler.search_by_keyword(keyword)
        article_urls = self.url_parser.parse(html_content)
        return await self.wechat_crawler.goto_article(article_urls)
