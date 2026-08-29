import subprocess

import pytest

from src.infrastructure.claude_cli import ClaudeCli, ClaudeCliError


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


class TestComplete:
    def test_result_フィールドを返す(self, monkeypatch) -> None:
        recorded: dict = {}

        def fake_run(command, **kwargs):
            recorded["command"] = command
            recorded["kwargs"] = kwargs
            return _completed(stdout='{"result": "短縮名です"}')

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = ClaudeCli().complete("プロンプト")

        assert result == "短縮名です"
        assert recorded["command"][0] == "claude"
        assert "-p" in recorded["command"]
        assert recorded["kwargs"]["input"] == "プロンプト"

    def test_モデルを指定できる(self, monkeypatch) -> None:
        recorded: dict = {}

        def fake_run(command, **kwargs):
            recorded["command"] = command
            return _completed(stdout='{"result": "ok"}')

        monkeypatch.setattr(subprocess, "run", fake_run)

        ClaudeCli(model="haiku").complete("プロンプト")

        command = recorded["command"]
        assert command[command.index("--model") + 1] == "haiku"

    def test_終了コードが0以外なら例外(self, monkeypatch) -> None:
        monkeypatch.setattr(
            subprocess, "run", lambda *a, **k: _completed(returncode=1, stderr="boom")
        )

        with pytest.raises(ClaudeCliError):
            ClaudeCli().complete("プロンプト")

    def test_標準出力がJSONでなければ例外(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(stdout="not json"))

        with pytest.raises(ClaudeCliError):
            ClaudeCli().complete("プロンプト")

    def test_resultフィールドが無ければ例外(self, monkeypatch) -> None:
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _completed(stdout="{}"))

        with pytest.raises(ClaudeCliError):
            ClaudeCli().complete("プロンプト")

    def test_タイムアウトすると例外(self, monkeypatch) -> None:
        def fake_run(*a, **k):
            raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(ClaudeCliError):
            ClaudeCli().complete("プロンプト")

    def test_claudeバイナリが無ければ例外(self, monkeypatch) -> None:
        def fake_run(*a, **k):
            raise FileNotFoundError("claude")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(ClaudeCliError):
            ClaudeCli().complete("プロンプト")

    def test_その他のOSErrorでも例外(self, monkeypatch) -> None:
        def fake_run(*a, **k):
            raise OSError("fork失敗")

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(ClaudeCliError):
            ClaudeCli().complete("プロンプト")
