"""
抖音搜索API测试脚本
使用 api_header.json（Cookie 已并入 headers）
"""
import json
import re
import sys
import requests

# 加载配置
with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

HEADERS = config["headers"]
SEARCH_PARAMS = config["search_params"]
SEARCH_URL = "https://www.douyin.com/aweme/v1/web/general/search/stream/"


def parse_stream_chunks(text: str) -> list:
    """解析抖音流式响应: hex_size\\nJSON\\n...0\\n\\n"""
    chunks = []
    markers = list(re.finditer(r'^([0-9a-fA-F]+)\r?\n', text, re.MULTILINE))
    for i, m in enumerate(markers):
        chunk_size = int(m.group(1), 16)
        if chunk_size == 0:
            break
        json_start = m.end()
        json_str = text[json_start:json_start + chunk_size]
        try:
            chunks.append(json.loads(json_str))
        except json.JSONDecodeError as e:
            if "Extra data" in str(e):
                for line in json_str.strip().split('\n'):
                    if line.strip().startswith('{'):
                        try:
                            chunks.append(json.loads(line.strip()))
                        except json.JSONDecodeError:
                            pass
    return chunks


def search(keyword: str, offset: int = 0):
    """调用抖音搜索接口"""
    params = {**SEARCH_PARAMS, "keyword": keyword, "offset": str(offset)}

    resp = requests.get(
        SEARCH_URL,
        params=params,
        headers=HEADERS,
        timeout=15,
    )

    print(f"=== 搜索: {keyword} ===")
    print(f"Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"响应: {resp.text[:500]}")
        return []

    chunks = parse_stream_chunks(resp.text.strip())
    print(f"解析到 {len(chunks)} 个 chunk")

    # 聚合所有 data
    all_items = []
    for chunk in chunks:
        if isinstance(chunk, dict) and "data" in chunk:
            all_items.extend(chunk["data"])

    # 输出摘要
    print(f"结果数: {len(all_items)}")
    for i, item in enumerate(all_items[:5]):
        aweme = item.get("aweme_info") or item
        images = aweme.get("images") or []
        atype = "图文" if images else "视频"
        title = aweme.get("desc", "")[:60]
        author = (aweme.get("author", {}) or {}).get("nickname", "")
        print(f"  [{i+1}] [{atype}] {title}  |  {author}")

    # 输出第一条完整 JSON
    if all_items:
        print(f"\n=== 第1条 aweme_info ===")
        print(json.dumps(all_items[0].get("aweme_info", all_items[0]), ensure_ascii=False, indent=2)[:2000])

    print("---\n")
    return all_items


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "故意伤害"
    search(kw)
