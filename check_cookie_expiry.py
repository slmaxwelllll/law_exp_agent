"""检查抖音 cookies 过期时间"""
import json
import urllib.parse
from datetime import datetime, timezone, timedelta

with open("api_header.json", "r", encoding="utf-8") as f:
    config = json.load(f)

raw = config["raw_cookie"]

cookies = {}
for item in raw.split("; "):
    if "=" in item:
        k, v = item.split("=", 1)
        cookies[k] = v

# sid_guard: sessionid|login_ts|duration_sec|expiry_date_str
sg = cookies.get("sid_guard", "")
beijing = timezone(timedelta(hours=8))

if sg:
    sg = urllib.parse.unquote(sg)
    parts = sg.split("|")
    print(f"sid_guard 解析:")
    print(f"  session_id  = {parts[0][:30]}...")
    
    # 时间戳 1780466290 是秒级 Unix epoch
    login_ts = int(parts[1])
    login_dt = datetime.fromtimestamp(login_ts, tz=timezone.utc)
    print(f"  login_ts    = {parts[1]} (epoch秒)")
    print(f"  login_time  = {login_dt} UTC")
    
    duration_sec = int(parts[2])
    print(f"  duration    = {duration_sec} 秒 ({duration_sec // 86400} 天)")
    print(f"  expiry_raw  = {parts[3]}")
print()

# login_time (毫秒)
lt = cookies.get("login_time", "")
if lt:
    ts_ms = int(lt)
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    print(f"login_time (ms) = {lt}")
    print(f"               = {dt} UTC")
print()

# 过期判断
now = datetime.now(timezone.utc)
print(f"当前时间 (UTC) = {now.strftime('%Y-%m-%d %H:%M:%S')}")

if sg and len(parts) >= 4:
    expiry_str = parts[3].replace("+", " ")
    expiry = datetime.strptime(expiry_str, "%a, %d-%b-%Y %H:%M:%S %Z")
    expiry = expiry.replace(tzinfo=timezone.utc)
    remaining = expiry - now
    print(f"cookie 过期    = {expiry.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"剩余时间       = {remaining.days} 天 {remaining.seconds // 3600} 小时 {remaining.seconds % 3600 // 60} 分钟")
    print()

    if remaining.total_seconds() > 7 * 86400:
        print("=" * 60)
        print("结论: Cookie 有效期还有约 60 天, 暂时不需要处理刷新问题")
        print("建议: 先聚焦跑通采集→模板构造的完整管道")
        print("      在 cookie 过期前 7 天加个告警/自动刷新即可")
        print("=" * 60)
    elif remaining.total_seconds() > 0:
        print(f"注意: Cookie 还剩 {remaining.days} 天, 建议着手准备刷新方案")
    else:
        print("!!! Cookie 已过期, 需要立即刷新 !!!")
