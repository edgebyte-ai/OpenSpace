from __future__ import annotations

from typing import Dict

from .base import BaseCLIAdapter
from .claude_code import ClaudeCodeCLIAdapter
from .codex import CodexCLIAdapter
from .copilot import CopilotCLIAdapter
from .cursor import CursorCLIAdapter

_ADAPTERS: Dict[str, BaseCLIAdapter] = {
    "codex": CodexCLIAdapter(),
    "copilot": CopilotCLIAdapter(),
    "cursor": CursorCLIAdapter(),
    "claude_code": ClaudeCodeCLIAdapter(),
    "claude-code": ClaudeCodeCLIAdapter(),
    "claudecode": ClaudeCodeCLIAdapter(),
}


def get_cli_adapter(name: str) -> BaseCLIAdapter:
    key = (name or "").strip().lower()
    if key in _ADAPTERS:
        return _ADAPTERS[key]
    # fallback: use codex semantics for unknown adapters
    return CodexCLIAdapter()
