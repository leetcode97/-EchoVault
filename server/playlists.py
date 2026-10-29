# -*- coding: utf-8 -*-
"""🏆 EchoVault 歌单模块。

歌单 = 纯引用列表：tracks 里存的是歌曲的「相对 music 目录路径」。
- 不复制音乐文件，一首歌的路径可出现在任意多个歌单
- 用相对路径而不是扫描 hash id：本地与服务器路径不同，hash 会变；
  相对路径（如 "我都明白 - 范倪Liu.mp3"）在两端一致，可跨端同步
- playlists.json 缺失时自动生成默认歌单：Alive / soft / sing
"""
import json
import os
import threading
from pathlib import Path

DEFAULT_PLAYLISTS = ["Alive", "soft", "sing"]


def _default_data():
    return {
        "version": 1,
        "playlists": [{"name": n, "tracks": []} for n in DEFAULT_PLAYLISTS],
    }


class PlaylistStore:
    """读写 playlists.json，线程安全，原子写入。"""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self):
        if not self.path.exists():
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._save(_default_data())
            except Exception:
                pass

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            data = None
        if not data or not isinstance(data.get("playlists"), list):
            data = _default_data()
        return data

    def _save(self, data):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def list_playlists(self):
        with self._lock:
            return self._load()["playlists"]

    def add_track(self, name: str, track_path: str) -> bool:
        with self._lock:
            data = self._load()
            for pl in data["playlists"]:
                if pl["name"] == name:
                    if track_path not in pl["tracks"]:
                        pl["tracks"].append(track_path)
                        self._save(data)
                    return True
            data["playlists"].append({"name": name, "tracks": [track_path]})
            self._save(data)
            return True

    def remove_track(self, name: str, track_path: str) -> bool:
        with self._lock:
            data = self._load()
            for pl in data["playlists"]:
                if pl["name"] == name and track_path in pl["tracks"]:
                    pl["tracks"].remove(track_path)
                    self._save(data)
                    return True
            return False
