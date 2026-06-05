"""最小 headers 测试：仅 Cookie + UA 是否足够"""
import json, re, requests

with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

cookie = config["headers"]["Cookie"]
ua = config["headers"]["User-Agent"]
params = {**config["search_params"], "keyword": "故意伤害", "offset": "0"}
url = "https://www.douyin.com/aweme/v1/web/general/search/stream/"

# 仅 Cookie + UA
min_headers = {"Cookie": cookie, "User-Agent": ua}

print("=== 测试: 仅 Cookie + User-Agent ===")
resp = requests.get(url, params=params, headers=min_headers, timeout=15)
print(f"Status: {resp.status_code}  |  响应长度: {len(resp.text)}")

if resp.status_code == 200:
    text = resp.text.strip()
    chunks = []
    for m in re.finditer(r'^([0-9a-fA-F]+)\r?\n', text, re.MULTILINE):
        sz = int(m.group(1), 16)
        if sz == 0:
            break
        js = text[m.end():m.end() + sz]
        try:
            chunks.append(json.loads(js))
        except:
            for line in js.strip().split('\n'):
                if line.strip().startswith('{'):
                    try:
                        chunks.append(json.loads(line.strip()))
                    except:
                        pass

    items = []
    for c in chunks:
        if isinstance(c, dict) and "data" in c:
            items.extend(c["data"])

    print(f"结果数: {len(items)}")
    if items:
        a = items[0].get("aweme_info", items[0])
        print(f"第1条标题: {a.get('desc', '')[:60]}")
        print("\n>>> 结论: 仅 Cookie + UA 就足够 <<<")
    else:
        print("\n>>> 有响应但无结果，可能需要额外 headers <<<")
else:
    print(f"失败: {resp.text[:300]}")
    print("\n>>> Cookie + UA 不够，需要完整 headers <<<")
