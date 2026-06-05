# 解析json数据
# 这里只持久化视频链接
import json
import os
import sys
from pathlib import Path

def parse_douyin_data(data: dict) -> list[dict]:
    """解析抖音返回的json数据，返回视频信息列表"""
    result = []
    for item in data.get("data", []):
        aweme = item.get("aweme_info", {})
        record = {
            "aweme_id": aweme.get("aweme_id"),
            "desc": aweme.get("desc", ""),
            "create_time": aweme.get("create_time"),
            # 出处
            "author_name": (aweme.get("author") or {}).get("nickname", ""),
            "author_verified": (aweme.get("author") or {}).get("custom_verify", ""),
            # 内容链接
            "images": [
                img["url_list"][0]
                for img in (aweme.get("images") or [])
                if img.get("url_list")
            ],
            "video_url": (
                aweme.get("video", {}).get("play_addr", {}).get("url_list", [None])[0]
            ),
        }
        result.append(record)

    with open("douyin_data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    return result