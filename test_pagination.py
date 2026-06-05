import json, re, requests

with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

params = config["search_params"].copy()
headers = config["headers"]
url = "https://www.douyin.com/aweme/v1/web/general/search/stream/"


def fetch(keyword, count, offset):
    params["keyword"] = keyword
    params["count"] = str(count)
    params["offset"] = str(offset)
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    text = resp.text.strip()
    chunks = []
    for m in re.finditer(r'^([0-9a-fA-F]+)\r?\n', text, re.MULTILINE):
        sz = int(m.group(1), 16)
        if sz == 0: break
        js = text[m.end():m.end() + sz]
        try: chunks.append(json.loads(js))
        except:
            for line in js.strip().split('\n'):
                if line.strip().startswith('{'):
                    try: chunks.append(json.loads(line.strip()))
                    except: pass
    items = []
    for c in chunks:
        if isinstance(c, dict) and "data" in c:
            items.extend(c["data"])
    return len(items), len(resp.text)


print("关键词          count  offset  返回条数  响应长度")
for kw, cnt, off in [
    ("故意伤害", 10, 0), ("故意伤害", 20, 0), ("故意伤害", 30, 0),
    ("故意伤害", 10, 10), ("故意伤害", 10, 20),
    ("法律", 20, 0), ("法律", 20, 10),
]:
    n, l = fetch(kw, cnt, off)
    print(f"{kw:10s}  {cnt:5d}  {off:5d}  {n:6d}  {l:7d}")
