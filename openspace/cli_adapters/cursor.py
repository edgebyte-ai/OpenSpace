from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseCLIAdapter, CLIParseResult, JSONLSessionMixin


class CursorCLIAdapter(BaseCLIAdapter, JSONLSessionMixin):
    name = "cursor"

    def default_command(self) -> List[str]:
        # Cursor Agent CLI naming varies by installation.
        # Allow OPENSPACE_CURSOR_CLI_COMMAND override to set the exact command.
        return ["cursor-agent", "run"]

    def parse_execution_output(
        self,
        output_text: str,
        workspace_dir: Optional[str] = None,
    ) -> CLIParseResult:
        cursor_home = Path(os.environ.get("CURSOR_HOME", str(Path.home() / ".cursor")))
        events = self.parse_session_jsonl(cursor_home / "sessions")
        base = super().parse_execution_output(output_text, workspace_dir)
        if events:
            tool_execs = self.events_to_tool_executions(events[-400:])
            if base.tool_executions:
                tool_execs.extend(base.tool_executions)
            return CLIParseResult(
                execution_report=base.execution_report,
                tool_executions=tool_execs,
            )
        return base
