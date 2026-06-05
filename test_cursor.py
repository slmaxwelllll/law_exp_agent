import json, re, requests

with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

params = config["search_params"].copy()
headers = config["headers"]
url = "https://www.douyin.com/aweme/v1/web/general/search/stream/"


def fetch(kw, extra=None):
    p = {**params, "keyword": kw, "count": "10", "offset": "0"}
    if extra:
        p.update(extra)
    resp = requests.get(url, params=p, headers=headers, timeout=15)
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
    cur = None
    more = None
    nil = None
    for c in chunks:
        if isinstance(c, dict):
            if "data" in c:
                items.extend(c["data"])
            if "cursor" in c:
                cur = c["cursor"]
            if "has_more" in c:
                more = c["has_more"]
            if "search_nil_info" in c:
                nil = c["search_nil_info"].get("search_nil_type", "")
    return items, cur, more, nil


# === 第1页: cursor=0 ===
items1, cur, more, nil = fetch("故意伤害", {"cursor": "0"})
print(f"=== page1 (cursor=0) ===")
print(f"返回: {len(items1)} 条  cursor={cur}  has_more={more}  nil_type={nil}")
if items1:
    print(f"  第1条: {items1[0].get('aweme_info',{}).get('desc','')[:50]}")
    print(f"  最后1条: {items1[-1].get('aweme_info',{}).get('desc','')[:50]}")

# === 第2页: cursor传上一页的cursor值 ===
if cur and more:
    cursor_val = cur
    items2, cur, more, nil = fetch("故意伤害", {"cursor": str(cursor_val)})
    print(f"\n=== page2 (cursor={cursor_val}) ===")
    print(f"返回: {len(items2)} 条  cursor={cur}  has_more={more}  nil_type={nil}")
    if items2:
        print(f"  第1条: {items2[0].get('aweme_info',{}).get('desc','')[:50]}")
        print(f"  最后1条: {items2[-1].get('aweme_info',{}).get('desc','')[:50]}")

        # 第三页
        if cur and more:
            cursor_val = cur
            items3, cur, more, nil = fetch("故意伤害", {"cursor": str(cursor_val)})
            print(f"\n=== page3 (cursor={cursor_val}) ===")
            print(f"返回: {len(items3)} 条  cursor={cur}  has_more={more}  nil_type={nil}")
            if items3:
                print(f"  第1条: {items3[0].get('aweme_info',{}).get('desc','')[:50]}")
    else:
        print("  翻页失败，再看原始响应:")
        # debug
        p = {**params, "keyword": "故意伤害", "count": "10", "cursor": str(cursor_val)}
        resp = requests.get(url, params=p, headers=headers, timeout=15)
        print(f"  status={resp.status_code}  len={len(resp.text)}")
        print(f"  body: {resp.text[:500]}")
else:
    print("\n警告: has_more=0 或 cursor 为空，无法翻页")
