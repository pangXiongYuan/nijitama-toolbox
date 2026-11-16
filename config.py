# -*- coding: utf-8 -*-
"""配置持久化：data/config.json

1.7.0 起改成「按副本入口分组」：
    入口(entry) → 话(chapter) → 关卡(stages / selected)
旧配置（1.6.x 的 stage_type/stage_title/junreki_stages…）在 load() 里自动搬过来，
只搬一次，搬完把旧键删掉。
"""
import json

import paths

HERE = paths.HERE
DATA = paths.DATA_DIR
CFG_FILE = DATA / "config.json"

CONFIG_VERSION = 2

DEFAULTS = {
    "config_version": CONFIG_VERSION,
    "entry": "junreki",        # junreki / ayakashi / summer / weekday
    "entries": {},             # 每个入口的缓存，用 get_entry() 取
    "lang_mode": "auto",       # auto=双语容忍 / ja=日文 / zh=中文（已装汉化）
    "stage_order": "picked",   # picked=按勾选先后 / list=按关卡列表顺序
    "runs": 5,
    "interval": 2.0,
    "mode": "attach",          # attach=普通（先自己开游戏）/ oneclick=一条龙
    "after": "keep",           # keep=留在游戏 / close=关闭游戏
    "cdp_port": 9222,
    "headless": False,
    "sound": True,             # 启动时打开声音（无头模式强制静音）
    "gpu": True,               # 旧字段，只为兼容老配置，读的时候由 gpu_mode 覆盖
    "gpu_mode": "auto",        # auto=交给 Chrome / force=强制独显 D3D11 / swiftshader=软件渲染
    "window_mode": "small",    # small=小窗口(960x540) / max=全屏最大化
    "show_help_on_start": True,   # 启动时是否自动弹出帮助（勾选不再提示后为 False）
    "weekday_remind_day": "",  # 哪天已经弹过「该刷新曜日任務」的提醒
}


def load() -> dict:
    DATA.mkdir(exist_ok=True)
    cfg = dict(DEFAULTS)
    saved = {}
    try:
        if CFG_FILE.exists():
            saved = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
    except Exception:
        saved = {}
    # 老配置没有 config_version，或还留着 stage_type 这些扁平键 → 搬一次并存回去
    if (not saved.get("config_version")) or ("stage_type" in cfg):
        cfg = _migrate(cfg)
        save(cfg)
    return cfg


def save(cfg: dict) -> None:
    DATA.mkdir(exist_ok=True)
    try:
        CFG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


# ---------- 入口缓存 ----------
def get_entry(cfg: dict, entry: str) -> dict:
    """取某个入口的缓存，缺什么补什么（只改内存，调用方自己 save）"""
    entries = cfg.setdefault("entries", {})
    e = entries.setdefault(entry, {})
    for k, v in (("chapters", []), ("chapter", {}), ("stage_lists", {}),
                 ("selected", {}), ("stages", []), ("day", "")):
        e.setdefault(k, v)
    return e


def ckey(chapter: dict) -> str:
    """话的唯一键：标题 + 副标题（副标题是「第一话」这种，用来区分重名）"""
    c = chapter or {}
    return "%s\x00%s" % (c.get("title", ""), c.get("sub", ""))


def entry_stages(cfg: dict, entry: str) -> list:
    """当前选中的话里，读到的全部关卡"""
    e = get_entry(cfg, entry)
    if entry == "weekday":
        return e.get("stages") or []
    return (e.get("stage_lists") or {}).get(ckey(e.get("chapter")), []) or []


def entry_selected(cfg: dict, entry: str) -> list:
    """当前选中的话里，勾了要刷的关卡（保持勾选顺序）"""
    e = get_entry(cfg, entry)
    if entry == "weekday":
        return e.get("selected") or []
    return (e.get("selected") or {}).get(ckey(e.get("chapter")), []) or []


def set_entry_selected(cfg: dict, entry: str, items: list) -> None:
    e = get_entry(cfg, entry)
    if entry == "weekday":
        e["selected"] = list(items)
    else:
        e.setdefault("selected", {})[ckey(e.get("chapter"))] = list(items)


def _migrate(cfg: dict) -> dict:
    """1.6.x 的扁平配置 → 2 的入口结构（由 load() 在检测到旧键时调用）"""
    entries = cfg.get("entries") or {}
    old_type = cfg.get("stage_type", "junreki")
    title = cfg.get("stage_title", "")
    sub = cfg.get("stage_sub", "")

    if old_type == "weekday":
        wk = entries.setdefault("weekday", {})
        if not wk.get("stages"):
            wk["stages"] = cfg.get("weekday_stages") or []
        if not wk.get("day"):
            wk["day"] = cfg.get("weekday_day", "")
        if not wk.get("selected") and title:
            wk["selected"] = [{"title": title, "sub": sub}]
        cfg["entry"] = "weekday"
    else:
        jk = entries.setdefault("junreki", {})
        if not jk.get("stage_lists") and cfg.get("junreki_stages"):
            # 老配置没有「话」这一层，全算作第一话的
            jk["stage_lists"] = {ckey({"title": "", "sub": ""}): cfg["junreki_stages"]}
        if title:
            jk["chapter"] = jk.get("chapter") or {}
            jk.setdefault("selected", {})
            jk["selected"].setdefault(ckey(jk.get("chapter")),
                                      [{"title": title, "sub": sub}])
        cfg["entry"] = "junreki"

    cfg["entries"] = entries
    cfg["config_version"] = CONFIG_VERSION
    for k in ("stage_type", "stage_title", "stage_sub", "stage_idx",
              "stage_keywords", "junreki_stages", "weekday_stages", "weekday_day"):
        cfg.pop(k, None)
    return cfg
