"""检查抖音搜索结果中一条原始 JSON 结构，输出到文件"""
import re
import json

with open("debug_response.txt", "r", encoding="utf-8") as f:
    text = f.read()

markers = list(re.finditer(r'^([0-9a-fA-F]+)\r?\n', text, re.MULTILINE))

all_chunks = []
for i, m in enumerate(markers):
    hex_size = m.group(1)
    chunk_size = int(hex_size, 16)
    if chunk_size == 0:
        break
    json_start = m.end()
    json_end = json_start + chunk_size
    if json_end > len(text):
        json_end = len(text)
    json_str = text[json_start:json_end]

    try:
        all_chunks.append(json.loads(json_str))
    except json.JSONDecodeError as e:
        if "Extra data" in str(e):
            for line in json_str.strip().split('\n'):
                line = line.strip()
                if line.startswith('{'):
                    try:
                        all_chunks.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        elif i + 1 < len(markers):
            next_start = markers[i + 1].start()
            json_str2 = text[json_start:next_start].rstrip('\r\n')
            try:
                all_chunks.append(json.loads(json_str2))
            except json.JSONDecodeError:
                pass

all_items = []
for chunk in all_chunks:
    if "data" in chunk and isinstance(chunk["data"], list):
        all_items.extend(chunk["data"])

print(f"解析到 {len(all_chunks)} 个 chunk, 共 {len(all_items)} 条结果")

# 每条取 aweme_info，收集 key 统计
all_keys = set()
for item in all_items:
    aweme = item.get("aweme_info", item)
    all_keys.update(aweme.keys())

print(f"\naweme_info 的所有字段 ({len(all_keys)} 个):")
for k in sorted(all_keys):
    print(f"  {k}")

# 输出前 2 条完整 JSON 到文件
with open("aweme_sample.json", "w", encoding="utf-8") as f:
    for idx in range(min(2, len(all_items))):
        item = all_items[idx]
        aweme = item.get("aweme_info", item)
        f.write(f"=== 第 {idx+1} 条 ===\n")
        f.write(json.dumps(aweme, ensure_ascii=False, indent=2))
        f.write("\n\n")

print("\n前 2 条完整 JSON 已保存到 aweme_sample.json")
