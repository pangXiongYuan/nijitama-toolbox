# -*- coding: utf-8 -*-
"""
启动引导：确保 playwright / requests 所在的 site-packages 在 sys.path 中。

微软商店版 Python 会把 `pip install --user` 的包装到
`%LOCALAPPDATA%\Packages\PythonSoftwareFoundation...\LocalCache\local-packages\Python3xx\site-packages`，
某些环境下该目录不会自动进入 sys.path，导致 `import playwright` 报 No module named。

用法：在每个脚本最顶部（导入 playwright 之前）写一行 `import _bootstrap`。
"""

import os
import sys
from pathlib import Path


def _find_store_user_site():
    # 1) 已通过 PYTHONPATH 指定
    p = os.environ.get("PYTHONPATH")
    if p:
        return p.split(os.pathsep)[0]

    # 2) 商店版 Python 的 LocalCache 用户 site-packages
    base = os.environ.get("LOCALAPPDATA") or ""
    root = Path(base) / "Packages"
    if root.is_dir():
        for d in root.iterdir():
            if d.name.startswith("PythonSoftwareFoundation"):
                lp = d / "LocalCache" / "local-packages"
                if lp.is_dir():
                    # Python311 / Python312 ... 取版本号最大的
                    for v in sorted(lp.iterdir(), reverse=True):
                        sp = v / "site-packages"
                        if sp.is_dir():
                            return str(sp)
    return None


def ensure():
    p = _find_store_user_site()
    if p and p not in sys.path:
        sys.path.insert(0, p)
    return p


ensure()
