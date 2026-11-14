# -*- coding: utf-8 -*-
"""配置持久化：data/config.json"""
import json

import paths

HERE = paths.HERE
DATA = paths.DATA_DIR
CFG_FILE = DATA / "config.json"

DEFAULTS = {
    "stage_type": "junreki",  # junreki=净化巡历 / weekday=曜日任務
    "stage_title": "武蔵国　江戸　火事",
    "stage_sub": "戦場　其の四",
    "stage_idx": 3,           # 关卡在列表中的序号（汉化后靠它兜底定位）
    "lang_mode": "auto",      # auto=双语容忍 / ja=日文 / zh=中文（已装汉化）
    "stage_keywords": ["江戸", "火事"],
    "runs": 5,
    "interval": 2.0,
    "mode": "attach",        # attach=普通（先自己开游戏）/ oneclick=一条龙
    "after": "keep",         # keep=留在游戏 / close=关闭游戏
    "cdp_port": 9222,
    "headless": False,
    "sound": True,            # 启动时打开声音（无头模式强制静音）
    "gpu": True,               # 旧字段，只为兼容老配置，读的时候由 gpu_mode 覆盖
    "gpu_mode": "auto",        # auto=交给 Chrome / force=强制独显 D3D11 / swiftshader=软件渲染
    "window_mode": "small",   # small=小窗口(960x540) / max=全屏最大化
    "show_help_on_start": True,   # 启动时是否自动弹出帮助（勾选不再提示后为 False）
    # 关卡列表缓存
    "junreki_stages": [],     # 净化巡历：永久保存
    "weekday_stages": [],     # 曜日任務：每晚 23:00 过期
    "weekday_day": "",        # 这份曜日缓存属于哪个游戏日
    "weekday_remind_day": "",  # 哪天已经弹过「该刷新曜日任務」的提醒
}


def load() -> dict:
    DATA.mkdir(exist_ok=True)
    cfg = dict(DEFAULTS)
    try:
        if CFG_FILE.exists():
            saved = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                cfg.update(saved)
    except Exception:
        pass
    return cfg


def save(cfg: dict) -> None:
    DATA.mkdir(exist_ok=True)
    try:
        CFG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
