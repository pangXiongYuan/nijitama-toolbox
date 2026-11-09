# -*- coding: utf-8 -*-
"""
paths.py —— 统一的路径定位

源码运行时：以本文件所在目录为基准
打包成 exe 后：以 exe 所在目录为基准（这样 profile/data 就在 exe 旁边）
"""
import sys
from pathlib import Path


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """打包后的只读资源目录（PyInstaller 解压到 _internal）"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", base_dir()))
    return Path(__file__).resolve().parent


HERE = base_dir()
PROFILE_DIR = HERE / "profile"
DATA_DIR = HERE / "data"
SHOTS_DIR = HERE / "steps"
ASSETS_DIR = resource_dir() / "assets"
