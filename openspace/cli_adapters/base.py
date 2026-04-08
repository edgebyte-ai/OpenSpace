from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CLIParseResult:
    execution_report: Optional[Dict[str, Any]]
    tool_executions: List[Dict[str, Any]]


class BaseCLIAdapter:
    name: str = "generic"

    def default_command(self) -> List[str]:
        raise NotImplementedError

    def env_command_key(self) -> str:
        return f"OPENSPACE_{self.name.upper()}_CLI_COMMAND"

    def resolve_command(self, explicit_command: Optional[str] = None) -> List[str]:
        if explicit_command and explicit_command.strip():
            return shlex.split(explicit_command)

        env_cmd = os.environ.get("OPENSPACE_AGENT_CLI_COMMAND", "").strip()
        if env_cmd:
            return shlex.split(env_cmd)

        by_name = os.environ.get(self.env_command_key(), "").strip()
        if by_name:
            return shlex.split(by_name)

        return self.default_command()

    def build_task_prompt(self, task: str, skill_context: str = "") -> str:
        prefix = "You are the primary execution agent.\n"
        if skill_context:
            prefix += (
                "Follow selected skill guidance below when relevant.\n\n"
                f"{skill_context}\n\n"
            )
        prefix += f"Original task:\n{task}\n"

        mcp_protocol = """
If MCP tools are available, use this explicit control protocol:
1) Call `cli_begin_execution` once before starting real actions.
2) After each meaningful action/tool, call `cli_report_step`.
3) If `cli_report_step` tells you to switch to fallback, do so.
4) Call `cli_finalize_execution` exactly once at the end.

If these MCP tools are not available in your runtime, continue execution normally.
"""

        report_contract = """
Before finishing, output an execution report as JSON in a fenced code block:
```json
{
  "summary": "<short result summary>",
  "steps": [
    {"tool": "<tool_or_action>", "status": "success|error", "detail": "<what happened>", "error": "<optional>"}
  ],
  "artifacts": ["<file or path>", "<url>"],
  "needs_followup": false
}
```
Use exact JSON.
"""
        return prefix + mcp_protocol + report_contract

    def parse_execution_output(
        self,
        output_text: str,
        workspace_dir: Optional[str] = None,
    ) -> CLIParseResult:
        report = self._extract_execution_report(output_text)
        if not report:
            return CLIParseResult(execution_report=None, tool_executions=[])
        return CLIParseResult(
            execution_report=report,
            tool_executions=self._steps_to_tool_executions(report.get("steps", [])),
        )

    def _extract_execution_report(self, text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        patterns = [
            r"```json\s*(\{[\s\S]*?\})\s*```",
            r"(\{[\s\S]*\"steps\"[\s\S]*\})",
        ]
        for pat in patterns:
            for m in re.finditer(pat, text):
                candidate = m.group(1).strip()
                try:
                    parsed = json.loads(candidate)
                except Exception:
                    continue
                if isinstance(parsed, dict) and "steps" in parsed:
                    return parsed
        return None

    def _steps_to_tool_executions(self, steps: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(steps, list):
            return out
        for step in steps:
            if not isinstance(step, dict):
                continue
            out.append(
                {
                    "tool_name": step.get("tool", "external_action"),
                    "status": step.get("status", "success"),
                    "error": step.get("error", ""),
                    "detail": step.get("detail", ""),
                }
            )
        return out


class JSONLSessionMixin:
    """Helper for CLIs that persist JSONL session events."""

    def parse_session_jsonl(self, sessions_dir: Path) -> List[Dict[str, Any]]:
        if not sessions_dir.exists():
            return []
        jsonl_files = sorted(sessions_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not jsonl_files:
            return []
        latest = jsonl_files[0]
        events: List[Dict[str, Any]] = []
        try:
            with latest.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        events.append(obj)
        except Exception:
            return []
        return events

    def events_to_tool_executions(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        tool_execs: List[Dict[str, Any]] = []
        for ev in events:
            t = str(ev.get("type", "")).lower()
            tag = str(ev.get("event", "")).lower()
            if ("tool" not in t) and ("tool" not in tag):
                continue
            name = (
                ev.get("tool")
                or ev.get("name")
                or ev.get("tool_name")
                or ev.get("action")
                or "external_action"
            )
            status = ev.get("status") or ("error" if ev.get("error") else "success")
            tool_execs.append(
                {
                    "tool_name": name,
                    "status": status,
                    "error": ev.get("error", ""),
                    "detail": ev.get("detail", "") or ev.get("message", ""),
                }
            )
        return tool_execs
