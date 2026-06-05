# 抖音爬虫服务类
# 接口: /aweme/v1/web/general/search/single/ (返回普通JSON，每页上限10条)
import json
import os
import sys
from pathlib import Path

# 包内相对导入路径修正: backend/douyin_service/ -> backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from manager.douyin_state_manager import DouyinStateManager

import requests

# 加载 URL 配置
_api_url_path = Path(__file__).resolve().parents[2] / "api_url.json"
with open(_api_url_path, "r", encoding="utf-8") as f:
    _url_config = json.load(f)

BASE_URL = _url_config["base_url"]
SEARCH_ENDPOINT = _url_config["search_endpoint"]

# 用 /search/single/ 覆盖 stream (返回普通JSON更好解析)
SEARCH_URL = BASE_URL + SEARCH_ENDPOINT


class DouyinCrawlService:
    def __init__(self):
        self.state_manager = DouyinStateManager()
        self.session = requests.Session()

    def search(self, keyword: str, offset: int = 0, count: int = 10) -> list[dict]:
        """调用抖音搜索接口，返回 aweme_info 列表"""
        params = {
            **self.state_manager.search_params,
            "keyword": keyword,
            "offset": str(offset),
            "count": str(count),
            "list_type": "single",
        }
        resp = self.session.get(
            SEARCH_URL,
            params=params,
            headers=self.state_manager.headers,
        )
        resp.raise_for_status()
        data = resp.json()
        with open("douyin_search.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    
