# -*- coding: utf-8 -*-
"""EchoVault 歌单 API 本地回归测试（一次性脚本）。"""
import json
import urllib.request
from urllib.parse import quote

BASE = "http://127.0.0.1:8848"


def req(method, url, body=None):
    data = json.dumps(body).encode("utf-8") if body else None
    r = urllib.request.Request(BASE + url, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


ok = True


def check(label, cond):
    global ok
    print(("✅" if cond else "❌"), label)
    if not cond:
        ok = False


lib = req("GET", "/api/library")[1]
t1 = lib["tracks"][0]["path"]
t2 = lib["tracks"][1]["path"]
print("t1 =", t1)
print("t2 =", t2)

# 加歌到 soft
s, _ = req("POST", "/api/playlists/soft/tracks", {"path": t2})
check(f"加歌到 soft -> {s}", s == 200)
# 重复加 soft（应去重）
s, _ = req("POST", "/api/playlists/soft/tracks", {"path": t2})
check(f"重复加歌去重 -> {s}", s == 200)
# 加不存在
s, d = req("POST", "/api/playlists/soft/tracks", {"path": "nope.mp3"})
check(f"加不存在的歌 -> {s} ({d.get('detail')})", s == 404)

# 歌单列表视图（join 曲库返回完整信息）
pls = req("GET", "/api/playlists")[1]["playlists"]
names = {p["name"]: p for p in pls}
check("三个歌单齐全", set(names) == {"Alive", "soft", "sing"})
check("soft 有 1 首", names["soft"]["count"] == 1)
check("join 返回完整歌曲信息", names["soft"]["tracks"][0]["title"] != "")
check("多归属: 同一首歌在 Alive 和 soft 各 1 首",
      names["Alive"]["count"] == 1 and names["soft"]["count"] == 1)

# 移出 soft
s, _ = req("DELETE", "/api/playlists/soft/tracks?path=" + quote(t2))
check(f"移出 soft -> {s}", s == 200)
pls = req("GET", "/api/playlists")[1]["playlists"]
names = {p["name"]: p for p in pls}
check("soft 移出后 0 首", names["soft"]["count"] == 0)
check("Alive 不受影响", names["Alive"]["count"] == 1)

# 移出不存在
s, d = req("DELETE", "/api/playlists/soft/tracks?path=" + quote(t2))
check(f"移出不存在的歌 -> {s}", s == 404)

# stream / cover 回归（path 相对化后；返回二进制，只查状态码）
t = lib["tracks"][0]
s, _ = req("GET", "/api/cover/" + t["id"])
check(f"cover 回归 -> {s}", s == 200)
s, _ = req("GET", "/api/stream/" + t["id"])
check(f"stream 回归 -> {s}", s == 200)

print("\n结论:", "全部通过 ✅" if ok else "存在失败 ❌")
