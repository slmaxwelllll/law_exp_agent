# 数据解析模块
# 解析策略：
#   SougouMetaParseStrategy → 搜狗搜索页 → 轻量元数据（管道1: ToolResult 反馈给 LLM）
#   HtmlParseStrategy       → 搜狗搜索页 → 文章相对 URL 列表（管道2: 模板构造）
#   JsonParseStrategy       → 文章详情页 → 结构化案例内容（管道2: 模板构造）

import re
from abc import abstractmethod, ABC
from bs4 import BeautifulSoup


class ParseStrategy(ABC):
    @abstractmethod
    def parse(self, response: str) -> list[dict]:
        """解析原始数据，返回解析后的数据列表"""
        pass


class SougouMetaParseStrategy(ParseStrategy):
    """搜狗搜索结果页 → 轻量元数据，用于 Tool Calling 反馈给 LLM"""
    
    def parse(self, response: str) -> list[dict]:
        soup = BeautifulSoup(response, "html.parser")
        articles = []
        for item in soup.select(".news-list li"):
            title_a = item.select_one("a[id^='sogou_vr_11002601_title_']")
            summary_p = item.select_one("p[id^='sogou_vr_11002601_summary_']")
            account_span = item.select_one("div.s-p span.all-time-y2")
            date_span = item.select_one("div.s-p span.s2")
            if not (title_a and summary_p):
                continue
            # 清洗 <em> 标签，获取纯文本
            title = title_a.get_text(strip=True)
            summary = summary_p.get_text(strip=True)
            account = account_span.get_text(strip=True) if account_span else ""
            date = self._clean_date(date_span.get_text(strip=True)) if date_span else ""
            articles.append({
                "title": title,
                "url": title_a["href"],
                "summary": summary,
                "account": account,
                "date": date,
            })
        return articles

    @staticmethod
    def _clean_date(text: str) -> str:
        """从 'document.write(timeConvert(...))2017-6-28' 中提取日期"""
        m = re.search(r"\d{4}-\d{1,2}-\d{1,2}", text)
        if m:
            return m.group(0)
        # 兜底：去除非日期文本
        cleaned = re.sub(r"document\.write.*?\)", "", text)
        return cleaned.strip()


class HtmlParseStrategy(ParseStrategy):
    """搜狗搜索结果页 → 文章相对 URL 列表，用于管道2逐篇跳转抓取正文"""

    def parse(self, response: str) -> list[str]:
        soup = BeautifulSoup(response, "html.parser")
        urls = []
        for item in soup.select(".news-list li"):
            a_tag = item.select_one("a[id^='sogou_vr_11002601_title_']")
            if a_tag and a_tag.get("href"):
                urls.append(a_tag["href"])
        return urls


class JsonParseStrategy(ParseStrategy):
    """文章详情页 JSON 数据 → 结构化案例内容（管道2 下游）"""

    def parse(self, response: str) -> list[dict]:
        pass