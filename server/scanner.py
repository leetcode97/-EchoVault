# -*- coding: utf-8 -*-
"""EchoVault 音乐库扫描器：递归扫描目录，读取元数据与内嵌封面。"""
import hashlib
import json
import os
import threading
from pathlib import Path

from mutagen import File as MFile

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}

# 常见的外部封面文件名（无内嵌封面时的兜底）
EXT_COVER_NAMES = {
    "cover.jpg", "cover.jpeg", "cover.png",
    "folder.jpg", "folder.jpeg", "folder.png",
    "front.jpg", "front.jpeg", "front.png",
    "albumart.jpg", "albumart.png",
}

SCAN_VERSION = 2  # 扫描逻辑版本；升级后强制全量重扫，避免旧缓存不生效

MIME_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _extract_cover(mf):
    """从 mutagen 对象提取内嵌封面，返回 (bytes, mime) 或 (None, None)。"""
    # FLAC / OGG 等使用 pictures
    try:
        pictures = getattr(mf, "pictures", None)
        if pictures:
            p = pictures[0]
            mime = getattr(p, "mime", None) or "image/jpeg"
            return bytes(p.data), mime
    except Exception:
        pass

    # MP3 ID3: APIC 帧
    try:
        tags = mf.tags
        if tags is not None:
            apic = tags.get("APIC:") or tags.get("APIC")
            if apic is not None:
                return bytes(apic.data), apic.mime
    except Exception:
        pass

    # M4A: covr
    try:
        tags = mf.tags
        if tags is not None and "covr" in tags:
            covr = tags["covr"]
            if covr:
                c = covr[0]
                return bytes(c), "image/jpeg"
    except Exception:
        pass
    return None, None


def _tag_str(tags, *keys):
    if tags is None:
        return ""
    for k in keys:
        try:
            v = tags.get(k)
        except Exception:
            continue
        if v is None:
            continue
        if isinstance(v, list):
            v = v[0] if v else None
        if v:
            s = str(v).strip()
            if s:
                return s
    return ""


def _tag_num(tags, *keys):
    if tags is None:
        return None
    for k in keys:
        try:
            v = tags.get(k)
        except Exception:
            continue
        if v is None:
            continue
        if isinstance(v, list):
            v = v[0] if v else None
        if v is not None:
            return int(v)
    return None


def _find_ext_cover(path: Path):
    """在同目录查找常见外部封面文件，返回相对 posix 路径或 None。"""
    for name in EXT_COVER_NAMES:
        p = path.parent / name
        if p.is_file():
            return p.as_posix()
    return None


def scan_track(path: Path):
    """扫描单个音频文件，返回 track dict 或 None。"""
    try:
        mf = MFile(str(path))
        if mf is None:
            return None
        tags = mf.tags
    except Exception:
        return None

    rel = path.as_posix()
    track_id = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:16]

    title = _tag_str(tags, "title", "©nam", "TIT2")
    artist = _tag_str(tags, "artist", "©ART", "TPE1")
    album = _tag_str(tags, "album", "©alb", "TALB")
    albumartist = _tag_str(tags, "albumartist", "aART", "TPE2")
    genre = _tag_str(tags, "genre", "©gen", "TCON")
    year = _tag_str(tags, "date", "©day", "TDRC", "TYER")

    if not title:
        title = path.stem

    try:
        duration = int(getattr(mf.info, "length", 0) or 0)
    except Exception:
        duration = 0
    try:
        bitrate = int(getattr(mf.info, "bitrate", 0) or 0)
    except Exception:
        bitrate = 0

    cover_data, cover_mime = _extract_cover(mf)
    ext_cover = _find_ext_cover(path) if cover_data is None else None

    return {
        "id": track_id,
        "path": rel,
        "title": title,
        "artist": artist or "未知艺术家",
        "album": album or "未知专辑",
        "albumartist": albumartist,
        "genre": genre,
        "year": year,
        "duration": duration,
        "bitrate": bitrate,
        "ext": path.suffix.lower(),
        "has_cover": cover_data is not None or ext_cover is not None,
        "ext_cover": ext_cover,
    }, (track_id, cover_data, cover_mime)


class MusicLibrary:
    """曲库：扫描 + JSON 缓存 + 封面磁盘缓存。"""

    def __init__(self, music_dir: Path, cache_file: Path, cover_dir: Path):
        self.music_dir = music_dir
        self.cache_file = cache_file
        self.cover_dir = cover_dir
        self.tracks = []
        self.by_id = {}
        self._lock = threading.Lock()
        self.scan_error = None
        self.scanned_at = None
        self.cover_dir.mkdir(parents=True, exist_ok=True)

    def _write_cover(self, track_id, data, mime):
        ext = MIME_TO_EXT.get(mime, ".jpg")
        target = self.cover_dir / f"{track_id}{ext}"
        if not target.exists():
            try:
                target.write_bytes(data)
            except Exception:
                return None
        return target

    def load_or_scan(self):
        """优先加载缓存；缓存缺失/版本不符/目录变化时重新扫描。"""
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                if data.get("scan_version") != SCAN_VERSION:
                    self.scan()
                    return
                self.tracks = data.get("tracks", [])
                self.scanned_at = data.get("scanned_at")
                self.by_id = {t["id"]: t for t in self.tracks}
                if self._cache_stale():
                    self.scan()
                return
            except Exception:
                pass
        self.scan()

    def _cache_stale(self):
        """音乐目录里音频或封面文件的修改时间晚于缓存生成时间 → 需要重扫。"""
        if not self.music_dir.exists():
            return False
        try:
            newest = max(
                (
                    p.stat().st_mtime
                    for p in self.music_dir.rglob("*")
                    if p.is_file()
                    and (p.suffix.lower() in AUDIO_EXTS or p.name.lower() in EXT_COVER_NAMES)
                ),
                default=0,
            )
        except Exception:
            return False
        return newest > (self.scanned_at or 0)

    def scan(self):
        with self._lock:
            self.tracks = []
            self.by_id = {}
            self.scan_error = None
            if not self.music_dir.exists():
                self.scan_error = f"音乐目录不存在: {self.music_dir}"
                self.scanned_at = 0
                return
            for p in sorted(self.music_dir.rglob("*"), key=lambda x: x.as_posix().lower()):
                if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
                    continue
                try:
                    result = scan_track(p)
                except Exception:
                    result = None
                if not result:
                    continue
                track, (tid, cover_data, cover_mime) = result
                if cover_data:
                    self._write_cover(tid, cover_data, cover_mime)
                self.tracks.append(track)
                self.by_id[track["id"]] = track
            import time
            self.scanned_at = time.time()
            self._save_cache()

    def _save_cache(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {"scan_version": SCAN_VERSION, "scanned_at": self.scanned_at, "tracks": self.tracks}
            tmp = self.cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.cache_file)
        except Exception:
            pass

    def get(self, track_id):
        return self.by_id.get(track_id)

    def cover_path(self, track_id):
        track = self.by_id.get(track_id)
        if not track or not track.get("has_cover"):
            return None
        # 1. 内嵌封面缓存优先
        for ext in (".jpg", ".png", ".webp", ".gif"):
            p = self.cover_dir / f"{track_id}{ext}"
            if p.exists():
                return p
        # 2. 外部封面文件兜底（cover.jpg / folder.jpg 等）
        if track.get("ext_cover"):
            p = self.music_dir / track["ext_cover"]
            if p.exists():
                return p
        return None

    def stats(self):
        total_sec = sum(t["duration"] for t in self.tracks)
        albums = len({t["album"] for t in self.tracks})
        artists = len({t["artist"] for t in self.tracks})
        return {
            "tracks": len(self.tracks),
            "total_seconds": total_sec,
            "albums": albums,
            "artists": artists,
            "scanned_at": self.scanned_at,
            "music_dir": str(self.music_dir),
            "error": self.scan_error,
        }
