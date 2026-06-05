import json, requests

with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

headers = config["headers"]
url = "https://www.douyin.com/aweme/v1/web/general/search/single/"
p = config["search_params"].copy()
p["list_type"] = "single"

print("=== /search/single/ 翻页测试 ===\n")
for offset in [0, 10, 20]:
    p["keyword"] = "故意伤害"
    p["offset"] = str(offset)
    p["count"] = "10"
    resp = requests.get(url, params=p, headers=headers, timeout=15)
    data = json.loads(resp.text.strip())
    items = data.get("data", [])
    print(f"offset={offset:3d}: {len(items)} 条  has_more={data.get('has_more')}  cursor={data.get('cursor')}  len={len(resp.text)}")
    for it in items[:3]:
        a = it.get("aweme_info", it)
        print(f"    {a.get('desc','')[:40]}")
    print()
