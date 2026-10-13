# -*- coding: utf-8 -*-
"""EchoVault 封面体检工具：检查音乐文件封面情况（内嵌封面 / 外部封面 / 无封面）。

用法:
    python tools/check_cover.py [音乐目录]      # 不传则默认项目下 music/
"""
import sys
from pathlib import Path

from mutagen import File as MFile

AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}
EXT_COVER_NAMES = {
    "cover.jpg", "cover.jpeg", "cover.png",
    "folder.jpg", "folder.jpeg", "folder.png",
    "front.jpg", "front.jpeg", "front.png",
    "albumart.jpg", "albumart.png",
}


def has_embedded_cover(mf):
    """检查 mutagen 对象是否带内嵌封面。"""
    try:
        if getattr(mf, "pictures", None):
            return True
    except Exception:
        pass
    try:
        tags = mf.tags
        if tags is not None:
            if tags.get("APIC:") or tags.get("APIC"):
                return True
            if "covr" in tags and tags["covr"]:
                return True
    except Exception:
        pass
    return False


def main(root: Path):
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS]
    if not files:
        print(f"目录里没有音频文件: {root}")
        return

    with_emb, with_ext, none = [], [], []
    for p in sorted(files):
        try:
            mf = MFile(str(p))
            if mf is not None and has_embedded_cover(mf):
                with_emb.append(p)
                continue
        except Exception:
            pass
        if any((p.parent / n).is_file() for n in EXT_COVER_NAMES):
            with_ext.append(p)
        else:
            none.append(p)

    print(f"共 {len(files)} 首 → 内嵌封面 {len(with_emb)} 首 · 外部封面 {len(with_ext)} 首 · 无封面 {len(none)} 首")
    if none:
        print("\n❌ 无封面（EchoVault 里会显示默认音符图标）:")
        for p in none:
            print("  " + str(p))
    if with_ext:
        print("\n✅ 仅靠外部 cover.jpg 兜底（文件本身没封面）:")
        for p in with_ext:
            print("  " + str(p))


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("music")
    main(root)
