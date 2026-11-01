# -*- coding: utf-8 -*-
"""EchoVault 音乐库扫描器：递归扫描目录，读取元数据与内嵌封面。"""
import hashlib
import json
import os
import re
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

SCAN_VERSION = 8  # 扫描逻辑版本；升级后强制全量重扫，避免旧缓存不生效

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


def _fix_mojibake(s: str) -> str:
    """修复 GBK 被错误解码为 Latin-1 的乱码。

    国内很多老 MP3 的 ID3 标签实际是 GBK 编码，但错误声明为 ISO-8859-1，
    导致 mutagen 按 Latin-1 解码后出现 °®μÄ·É... 这样的乱码。
    """
    if not s:
        return s
    # 如果已经有中文字符，说明解码正确，直接返回
    has_cjk = any(0x4E00 <= ord(c) <= 0x9FFF for c in s)
    if has_cjk:
        return s
    # 如果没有高位字符（纯 ASCII），也不需要修复
    has_high = any(ord(c) >= 0x80 for c in s)
    if not has_high:
        return s
    # 尝试修复：Latin-1 字符串编码回字节，再用 GBK 解码
    try:
        fixed = s.encode('latin-1').decode('gbk')
        # 修复成功的标志：至少有一个中文字符，且没有替换字符
        has_cjk_fixed = any(0x4E00 <= ord(c) <= 0x9FFF for c in fixed)
        if has_cjk_fixed and '�' not in fixed:
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s


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
                return _fix_mojibake(s)
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
    """查找外部封面，优先级：同名图片 → 去曲目号同名图片 → 通用封面名兜底。

    例如 `01 晴天.mp3` 会依次尝试：
      1) 01 晴天.jpg / 01 晴天.png / 01 晴天.jpeg（同名精确匹配）
      2) 晴天.jpg / 晴天.png（去掉 "01. " 前缀后再匹配）
      3) cover.jpg / folder.jpg / front.jpg ...（整个文件夹共享兜底）
    返回相对 posix 路径或 None。
    """
    stem = path.stem
    for ext in (".jpg", ".jpeg", ".png"):
        p = path.parent / (stem + ext)
        if p.is_file():
            return p.as_posix()
    m = re.match(r"^\d{1,3}[.\-_\s]+\s*(.*)$", stem)
    if m:
        core = m.group(1)
        for ext in (".jpg", ".jpeg", ".png"):
            p = path.parent / (core + ext)
            if p.is_file():
                return p.as_posix()
    for name in EXT_COVER_NAMES:
        p = path.parent / name
        if p.is_file():
            return p.as_posix()
    return None


# 文件名分隔符（按优先级尝试）：空格-空格、空格–空格、空格—空格、下划线等
_FILENAME_SEPS = (" - ", " – ", " — ", " _ ", "_", " -", "- ", "-", "–", "—")


def parse_filename(path: Path, fmt):
    """从文件名解析 (title, artist, album)。仅在文件缺少 ID3 标签时使用。

    fmt:
      - "artist-title": 文件名 = 歌手 - 歌名
      - "title-artist": 文件名 = 歌名 - 歌手
      - 三字段扩展：如果文件名里有两个分隔符，自动识别第三段为专辑
        - artist-title-album: 歌手 - 歌名 - 专辑
        - title-artist-album: 歌名 - 歌手 - 专辑
      - "none"        : 关闭，不做文件名解析
    支持 "01. 歌名 - 歌手.mp3" 这类带曲目号前缀的命名。
    """
    stem = path.stem
    # 去掉曲目号前缀：01. / 01- / 01_ / 01 空格
    m = re.match(r"^\s*\d{1,3}[.\-_\s]+\s*(.*)$", stem)
    if m:
        stem = m.group(1)
    if fmt == "none" or not stem:
        return stem or path.stem, "", ""
    for sep in _FILENAME_SEPS:
        if sep in stem:
            parts = [p.strip() for p in stem.split(sep) if p.strip()]
            # 三字段：歌名 - 歌手 - 专辑
            if len(parts) >= 3:
                first, second, third = parts[0], parts[1], parts[2]
                if "title-artist-album" in fmt:
                    return first, second, third   # 歌名 - 歌手 - 专辑
                if "artist-title-album" in fmt:
                    return second, first, third   # 歌手 - 歌名 - 专辑
            # 两字段
            if len(parts) == 2:
                first, second = parts[0], parts[1]
                if fmt == "title-artist":
                    return first, second, ""      # 歌名 - 歌手
                return second, first, ""          # 歌手 - 歌名
            break
    return stem, "", ""


def scan_track(path: Path, filename_format="artist-title"):
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

    # 标签缺失时，从文件名解析（"歌手 - 歌名" / "歌名 - 歌手 - 专辑"）
    fname_title, fname_artist, fname_album = parse_filename(path, filename_format)
    if not title:
        title = fname_title or path.stem
    if not artist:
        artist = fname_artist or "未知艺术家"
    if not album:
        album = fname_album or "未知专辑"

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

    def __init__(self, music_dir: Path, cache_file: Path, cover_dir: Path, filename_format="artist-title"):
        self.music_dir = music_dir
        self.cache_file = cache_file
        self.cover_dir = cover_dir
        self.filename_format = filename_format
        self.tracks = []
        self.by_id = {}
        self.by_path = {}
        self._lock = threading.Lock()
        self.scan_error = None
        self.scanned_at = None
        self._saved_fp = set()
        self.cover_dir.mkdir(parents=True, exist_ok=True)

    def _file_fingerprint(self):
        """当前音乐目录的文件清单指纹（音频+封面文件的 路径/大小/修改时间）。"""
        fp = set()
        for p in self.music_dir.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() in AUDIO_EXTS or p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                try:
                    st = p.stat()
                    fp.add((p.as_posix(), st.st_mtime, st.st_size))
                except Exception:
                    pass
        return fp

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
                self._saved_fp = set(tuple(x) for x in data.get("files", []))
                self.by_id = {t["id"]: t for t in self.tracks}
                self.by_path = {t["path"]: t for t in self.tracks}
                if self._cache_stale():
                    self.scan()
                return
            except Exception:
                pass
        self.scan()

    def _cache_stale(self):
        """音乐目录文件清单（增/删/改）与上次扫描不一致 → 需要重扫。"""
        if not self.music_dir.exists():
            return False
        return self._file_fingerprint() != self._saved_fp

    def scan_if_stale(self):
        """目录有新文件时自动重扫，返回是否发生了重扫。"""
        if self._cache_stale():
            self.scan()
            return True
        return False

    def scan(self):
        with self._lock:
            self.tracks = []
            self.by_id = {}
            self.by_path = {}
            self.scan_error = None
            if not self.music_dir.exists():
                self.scan_error = f"音乐目录不存在: {self.music_dir}"
                self.scanned_at = 0
                return
            self._saved_fp = self._file_fingerprint()
            for p in sorted(self.music_dir.rglob("*"), key=lambda x: x.as_posix().lower()):
                if not p.is_file() or p.suffix.lower() not in AUDIO_EXTS:
                    continue
                try:
                    result = scan_track(p, self.filename_format)
                except Exception:
                    result = None
                if not result:
                    continue
                track, (tid, cover_data, cover_mime) = result
                # path 归一化为相对 music_dir 的 posix 路径（本地/服务器一致，歌单引用可跨端同步）
                try:
                    track["path"] = p.relative_to(self.music_dir).as_posix()
                except Exception:
                    pass
                if track.get("ext_cover"):
                    try:
                        track["ext_cover"] = Path(track["ext_cover"]).relative_to(self.music_dir).as_posix()
                    except Exception:
                        pass
                if cover_data:
                    self._write_cover(tid, cover_data, cover_mime)
                self.tracks.append(track)
                self.by_id[track["id"]] = track
                self.by_path[track["path"]] = track
            import time
            self.scanned_at = time.time()
            self._save_cache()

    def _save_cache(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "scan_version": SCAN_VERSION,
                "scanned_at": self.scanned_at,
                "tracks": self.tracks,
                "files": [list(x) for x in sorted(self._saved_fp)],
            }
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
