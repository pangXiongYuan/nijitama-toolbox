# -*- coding: utf-8 -*-
"""
docwatch.py —— 说明文档自动留档

作用：程序运行期间定期检查说明文档的内容指纹，
      只要内容和上次不同，就把这一版存进 data/doc_history/。
      这样任何一次修改（包括被误覆盖之前的内容）都能找回来，
      而且不需要人工操作，也不消耗任何对话资源。

存储：按内容哈希命名，同样的内容只存一份，不会重复占空间。
      最多保留 50 个版本，超出的按时间从旧到新删除。
"""
import hashlib
import json
import time

import paths

# 需要监控的文档（源码版和打包版都覆盖）
WATCH = [
    ("使用说明.txt", lambda: paths.HERE / "使用说明.txt"),
    ("使用说明.txt", lambda: paths.HERE / "docs" / "使用说明.txt"),
    ("功能说明.md", lambda: paths.HERE / "docs" / "功能说明.md"),
    ("功能说明.txt", lambda: paths.HERE / "功能说明.txt"),
]

HISTORY_DIR = paths.DATA_DIR / "doc_history"
INDEX_FILE = paths.DATA_DIR / "doc_history.json"
MAX_KEEP = 50


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:10]


def _load_index() -> dict:
    try:
        if INDEX_FILE.exists():
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_index(idx: dict):
    try:
        paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_FILE.write_text(json.dumps(idx, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception:
        pass


def snapshot() -> list:
    """
    检查一遍所有文档，有新内容就存档。
    返回本次新存的条目列表 [{"name","file","hash","size"}]。
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    idx = _load_index()
    added = []

    for name, getter in WATCH:
        try:
            p = getter()
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
            if not text.strip():
                continue
            h = _sha(text)
            key = f"{name}::{h}"
            if key in idx:
                continue
            dst = HISTORY_DIR / f"{name}.{h}.txt"
            if not dst.exists():
                dst.write_text(text, encoding="utf-8")
            idx[key] = {
                "file": str(p),
                "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
                "size": len(text),
            }
            added.append({"name": name, "file": str(p), "hash": h,
                          "size": len(text)})
        except Exception:
            continue

    if added:
        # 控制数量：超出上限就从最旧的开始删
        items = sorted(idx.items(), key=lambda kv: kv[1].get("saved", ""))
        while len(items) > MAX_KEEP:
            key, meta = items.pop(0)
            try:
                p = HISTORY_DIR / f"{meta['file'].split(chr(92))[-1]}.{key.split('::')[1]}.txt"
                if p.exists():
                    p.unlink()
            except Exception:
                pass
            idx.pop(key, None)
        _save_index(idx)

    return added


def history() -> list:
    """列出已存档的版本，最新在前"""
    idx = _load_index()
    items = [{"name": k.split("::")[0], "hash": k.split("::")[1], **v}
             for k, v in idx.items()]
    return sorted(items, key=lambda x: x.get("saved", ""), reverse=True)
