#!/usr/bin/env python3
"""看雪山 MCP 服务器——日照金山预报，供任何 MCP 客户端调用。

工具：
- search_peak: 搜索山峰和观景点
- query_peaks: 按坐标查周边雪山预报
- forecast_peak: 某山峰未来 N 天金山预报
"""
import os, json, urllib.request, urllib.parse, datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API = os.environ.get("KXS_API", "http://127.0.0.1:3000")
# HOST 默认 0.0.0.0（本地开发需局域网访问）；生产 HOST=127.0.0.1 仅回环，nginx 反代 https://www.yilong.art/mcp
# transport_security：放行生产域名的 Host/Origin（否则 SDK 的 DNS rebinding 保护会拒经 nginx 的请求）
mcp = FastMCP(
    "kanxueshan",
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "3999")),
    transport_security=TransportSecuritySettings(
        allowed_hosts=["www.yilong.art", "yilong.art", "127.0.0.1:3999", "localhost:3999"],
        allowed_origins=["https://www.yilong.art", "https://yilong.art"],
    ),
)

def get(path):
    req = urllib.request.Request(f"{API}{path}", headers={"X-Client": "mcp"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def _fmt_peak(p):
    m, e = p.get("golden_morning"), p.get("golden_evening")
    f = p.get("visibility_factors") or {}
    lines = [f"{p['name']} {p['elevation']}m（{p['distance_km']}km）"]
    lines.append(f"日出金山: {m['start']}-{m['end']}" if m else "日出金山: 无")
    lines.append(f"日落金山: {e['start']}-{e['end']}" if e else "日落金山: 无")
    lines.append(f"评分: {p['visibility_rating']} {p['visibility_score']}分"
                 f"（云量{f['cloud']:.0f}% 湿度{f['humidity']:.0f}% 风速{f['wind']:.0f}km/h）")
    if p.get("visibility_tip"):
        lines.append(f"提示: {p['visibility_tip']}")
    return "\n".join(lines)

@mcp.tool()
def search_peak(name: str) -> str:
    """搜索中国雪山，返回匹配的山峰及其观景点（子梅垭口、飞来寺、台怀镇等）。
    参数 name: 山峰名关键词（贡嘎山、幺妹峰、卡瓦格博、慕士塔格等）。"""
    matches = get(f"/api/search?q={urllib.parse.quote(name)}").get("matches", [])
    if not matches:
        return f"未找到「{name}」，试试：贡嘎山、幺妹峰、卡瓦格博、玉珠峰、慕士塔格"
    out = []
    for m in matches[:5]:
        vps = "、".join(v["name"] for v in m.get("viewpoints", [])) or "推荐观景点"
        out.append(f"🏔️ {m['name_zh']} {m['elevation']}m 观景点：{vps}")
    return "\n".join(out)

@mcp.tool()
def query_peaks(lat: float, lng: float, date: str = "") -> str:
    """按经纬度查询周边可见雪山及今日日照金山预报（金光时段、0-100 评分、天气因子）。
    参数 lat/lng: WGS-84 十进制度坐标；date: YYYY-MM-DD，缺省今天。"""
    d = date or datetime.date.today().strftime("%Y-%m-%d")
    r = get(f"/api/peaks?lat={lat}&lng={lng}&date={d}&radius=200")
    visible = [p for p in r["peaks"] if p["visible"]]
    if not visible:
        return f"{lat}, {lng} 周边（{d}）无可见雪山"
    out = [f"📍 {lat}, {lng}（{d}）可见 {len(visible)} 座："]
    for p in visible[:8]:
        out.append(_fmt_peak(p))
    return "\n\n".join(out)

@mcp.tool()
def forecast_peak(peak: str, days: int = 7, viewpoint: str = "", date: str = "") -> str:
    """查询某山峰未来 N 天（1-7）的日照金山预报。
    参数 peak: 山峰名；days: 预报天数；viewpoint: 观景点名（可选，如子梅垭口）；
    date: 起始日期 YYYY-MM-DD，缺省今天。"""
    matches = get(f"/api/search?q={urllib.parse.quote(peak)}").get("matches", [])
    if not matches:
        return f"未找到「{peak}」"
    m = matches[0]
    vps = m.get("viewpoints") or []
    vp = None
    if viewpoint:
        vp = next((v for v in vps if viewpoint in v["name"]), None)
    if not vp:
        vp = vps[0] if vps else {"lat": m["lat"] - 0.09, "lng": m["lng"], "name": "推荐观景点"}
    start = date or datetime.date.today().strftime("%Y-%m-%d")
    days = max(1, min(days, 7))
    out = [f"📅 {m['name_zh']} · 📍 {vp.get('name','推荐观景点')} 未来 {days} 天预报："]
    for n in range(days):
        d = (datetime.date.fromisoformat(start) + datetime.timedelta(days=n)).isoformat()
        r = get(f"/api/peaks?lat={vp['lat']}&lng={vp['lng']}&date={d}&radius=200")
        p = next((x for x in r["peaks"] if x["name"] == m["name_zh"]), None)
        if not p:
            out.append(f"{d}：该观景点看不到此峰")
            continue
        out.append(f"【{d}】\n{_fmt_peak(p)}")
    return "\n\n".join(out)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
