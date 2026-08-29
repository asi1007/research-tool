from __future__ import annotations

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "haiku"
DEFAULT_TIMEOUT_SECONDS = 300


class ClaudeCliError(Exception):
    pass


class ClaudeCli:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        command = ["claude", "-p", "--model", self.model, "--output-format", "json"]

        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as error:
            raise ClaudeCliError(f"claude -p の実行に失敗しました: {error}") from error

        if completed.returncode != 0:
            raise ClaudeCliError(
                f"claude -p が異常終了しました: exit={completed.returncode} "
                f"stderr={completed.stderr.strip()}"
            )

        try:
            envelope = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ClaudeCliError(f"claude -p の出力がJSONではありません: {error}") from error

        result = envelope.get("result") if isinstance(envelope, dict) else None
        if not isinstance(result, str):
            raise ClaudeCliError("claude -p の出力にresultフィールドがありません")

        return result
