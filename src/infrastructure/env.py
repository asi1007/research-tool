from __future__ import annotations

import os


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"環境変数 {name} が設定されていません。.env を確認してください。")
    return value
