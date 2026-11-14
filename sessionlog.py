# -*- coding: utf-8 -*-
"""
sessionlog.py —— 滚动会话日志

界面上的日志关掉就没了。像「游戏卡死」这种没有异常堆栈的问题，
事后只能靠最后几行操作记录判断卡在哪一步。
所以把界面日志同时写一份到 data/session.log，超过上限就只留最近的。

只做追加和裁剪，任何异常都吞掉——日志坏了不能影响主流程。
"""
from datetime import datetime
from pathlib import Path

MAX_BYTES = 512 * 1024     # 超过这个大小就裁剪
KEEP_LINES = 3000          # 裁剪后保留最近多少行


def write(text: str, path: Path) -> None:
    """追加一行（或多行）带时间戳的日志"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%H:%M:%S")
        lines = str(text).splitlines() or [""]
        with path.open("a", encoding="utf-8") as f:
            for line in lines:
                f.write(f"[{stamp}] {line}\n")
        if path.stat().st_size > MAX_BYTES:
            _trim(path)
    except Exception:
        pass


def _trim(path: Path) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        path.write_text("\n".join(lines[-KEEP_LINES:]) + "\n", encoding="utf-8")
    except Exception:
        pass
