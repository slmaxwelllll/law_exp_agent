"""测试 search_id 是否解决翻页问题"""
import json, requests, time, random, string

with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

headers = config["headers"]
url = "https://www.douyin.com/aweme/v1/web/general/search/single/"
base_params = config["search_params"].copy()
base_params["list_type"] = "single"

# 生成 search_id: 时间戳 + 随机 hex
ts = time.strftime("%Y%m%d%H%M%S")
rand_hex = ''.join(random.choices(string.hexdigits.upper(), k=24))
search_id = ts + rand_hex
print(f"生成的 search_id: {search_id}\n")

base_params["search_id"] = search_id

for offset in [0, 10, 20]:
    p = {**base_params, "keyword": "故意伤害", "offset": str(offset), "count": "10"}
    resp = requests.get(url, params=p, headers=headers, timeout=15)
    data = json.loads(resp.text.strip())
    items = data.get("data", [])
    print(f"offset={offset:3d}: {len(items)} 条  has_more={data.get('has_more')}  cursor={data.get('cursor')}")
    for it in items[:2]:
        a = it.get("aweme_info", it)
        print(f"    {a.get('desc','')[:40]}")
    if not items:
        nil = data.get("search_nil_info", {})
        print(f"    nil_type={nil.get('search_nil_type')}")
    print()
