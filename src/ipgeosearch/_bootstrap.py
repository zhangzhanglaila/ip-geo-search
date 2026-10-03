"""Helpers for importing sibling repositories.

兄弟仓库（ip2region 的 Python binding、GeoIP2-python）需要加入导入搜索路径。
这里把它收敛成一处，并且重复调用不产生副作用——原来的实现每次懒加载都会
`sys.path.insert(0, ...)`，多次调用会累积重复路径项，且并发下修改全局状态。
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

_lock = threading.Lock()


def ensure_import_path(path: Path) -> None:
    """把目录加入导入搜索路径，已存在时不重复插入。"""
    entry = str(path)
    with _lock:
        if entry not in sys.path:
            sys.path.insert(0, entry)
