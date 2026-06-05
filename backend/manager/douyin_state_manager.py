# 抖音全局状态管理器
# 单例模式，负责从 api_header.json 加载请求配置
# Warning：至今没有构造cookies过期刷新机制，2026.6.3有效期还有59天
import json
from pathlib import Path

# api_header.json 位置：项目根目录（backend/agent/manager 往上三层）
_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "api_header.json"


class DouyinStateManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self._state = self._load()
        self.headers: dict = self._state.get("headers", {})
        self.search_params: dict = self._state.get("search_params", {})

    def _load(self) -> dict:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[DouyinStateManager] 加载失败: {e}")
            return {}
