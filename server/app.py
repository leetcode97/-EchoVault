# -*- coding: utf-8 -*-
"""🏆 EchoVault — 自托管个人音乐播放器服务端。

启动: uvicorn server.app:app --host 0.0.0.0 --port 8000
"""
import json
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .scanner import MusicLibrary

ROOT = Path(__file__).resolve().parent.parent


def load_config():
    cfg_path = ROOT / "config.json"
    defaults = {
        "music_dir": "music",
        "host": "0.0.0.0",
        "port": 8000,
        "library_cache": ".cache/library.json",
        "cover_cache": ".cache/covers",
    }
    if cfg_path.exists():
        try:
            user = json.loads(cfg_path.read_text(encoding="utf-8"))
            defaults.update(user)
        except Exception:
            pass
    # 环境变量优先（Docker 场景）
    import os
    if os.environ.get("MUSIC_DIR"):
        defaults["music_dir"] = os.environ["MUSIC_DIR"]
    if os.environ.get("EV_PORT"):
        defaults["port"] = int(os.environ["EV_PORT"])
    # music_dir 支持绝对路径或相对项目根
    md = Path(defaults["music_dir"])
    if not md.is_absolute():
        md = ROOT / md
    defaults["music_dir_abs"] = str(md.resolve())
    return defaults


CONFIG = load_config()

MUSIC_DIR = Path(CONFIG["music_dir_abs"])
CACHE_FILE = ROOT / CONFIG["library_cache"]
COVER_DIR = ROOT / CONFIG["cover_cache"]

library = MusicLibrary(MUSIC_DIR, CACHE_FILE, COVER_DIR)
library.load_or_scan()

app = FastAPI(title="EchoVault", version="1.0.0")

AUTO_RESCAN_INTERVAL = 20  # 秒；后台线程定期检查音乐目录变化并自动重扫


def _auto_rescan_loop():
    """后台自动检测：用户往音乐目录放新文件后，自动更新曲库。"""
    while True:
        time.sleep(AUTO_RESCAN_INTERVAL)
        try:
            library.scan_if_stale()
        except Exception:
            pass


threading.Thread(target=_auto_rescan_loop, daemon=True).start()


@app.get("/api/stats")
def api_stats():
    return library.stats()


@app.get("/api/library")
def api_library(q: str = Query(default="", max_length=200)):
    tracks = library.tracks
    if q:
        ql = q.lower()
        tracks = [
            t for t in tracks
            if ql in t["title"].lower()
            or ql in t["artist"].lower()
            or ql in t["album"].lower()
            or ql in t.get("genre", "").lower()
        ]
    return {"tracks": tracks, "total": len(tracks)}


@app.get("/api/albums")
def api_albums():
    groups = {}
    for t in library.tracks:
        key = (t["album"], t.get("albumartist") or t["artist"])
        groups.setdefault(key, []).append(t)
    albums = []
    for (name, artist), items in groups.items():
        items.sort(key=lambda t: (t.get("year") or "", t.get("track") or 0, t["title"].lower()))
        albums.append({
            "name": name,
            "artist": artist,
            "year": items[0].get("year") or "",
            "count": len(items),
            "cover_id": next((i["id"] for i in items if i.get("has_cover")), items[0]["id"]),
            "tracks": items,
        })
    albums.sort(key=lambda a: a["name"].lower())
    return {"albums": albums, "total": len(albums)}


@app.get("/api/artists")
def api_artists():
    groups = {}
    for t in library.tracks:
        key = t["albumartist"] or t["artist"]
        groups.setdefault(key, []).append(t)
    artists = []
    for name, items in groups.items():
        artists.append({
            "name": name,
            "count": len(items),
            "cover_id": next((i["id"] for i in items if i.get("has_cover")), items[0]["id"]),
            "tracks": items,
        })
    artists.sort(key=lambda a: a["name"].lower())
    return {"artists": artists, "total": len(artists)}


@app.get("/api/cover/{track_id}")
def api_cover(track_id: str):
    p = library.cover_path(track_id)
    if p is None:
        raise HTTPException(404, "no cover")
    return FileResponse(p)


MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
}


@app.get("/api/stream/{track_id}")
def api_stream(track_id: str):
    track = library.get(track_id)
    if track is None:
        raise HTTPException(404, "track not found")
    path = MUSIC_DIR / track["path"]
    if not path.exists():
        raise HTTPException(404, "file missing")
    return FileResponse(str(path), media_type=MEDIA_TYPES.get(track["ext"], "application/octet-stream"), filename=track["title"] + track["ext"])


@app.post("/api/rescan")
def api_rescan():
    library.scan()
    return library.stats()


@app.get("/api/config")
def api_config():
    return {"music_dir": str(MUSIC_DIR), "version": app.version}


# PWA 静态资源
app.mount("/", StaticFiles(directory=str(ROOT / "web"), html=True), name="web")
