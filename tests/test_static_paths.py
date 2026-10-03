"""静态文件路径解析测试：目录穿越防护。"""

from __future__ import annotations

import pytest

from ipgeosearch.server import STATIC_ROOT, resolve_static_path


def test_serves_existing_assets():
    assert resolve_static_path("/static/app.js") == (STATIC_ROOT / "app.js").resolve()
    assert resolve_static_path("/static/styles.css") is not None
    assert resolve_static_path("/static/assets/china-coordinates.json") is not None


def test_ignores_redundant_dot_segments():
    assert resolve_static_path("/static/./app.js") == (STATIC_ROOT / "app.js").resolve()
    assert resolve_static_path("/static//app.js") == (STATIC_ROOT / "app.js").resolve()


def test_returns_path_even_when_file_missing():
    # 是否存在的判断由调用方负责，这里只保证路径仍限定在静态目录内。
    resolved = resolve_static_path("/static/not-here.js")
    assert resolved is not None and resolved.is_relative_to(STATIC_ROOT.resolve())


@pytest.mark.parametrize(
    "url_path",
    [
        "/static/../README.md",
        "/static/../pyproject.toml",
        "/static/..%2fREADME.md",
        "/static/%2e%2e/README.md",
        "/static/assets/../../README.md",
        "/static/../../etc/passwd",
        "/static/../static_extra/app.js",
        "/static/..\\README.md",
        "/static/",
        "/static",
        "/static/app.js/../../README.md",
        "/other/app.js",
        "/",
    ],
)
def test_rejects_traversal_and_non_static_paths(url_path: str):
    assert resolve_static_path(url_path) is None
