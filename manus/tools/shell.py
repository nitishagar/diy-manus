"""Shell tool: merged output pipe, incremental bounded read, process-group reaping."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import time

from manus.tools.base import Tool, ToolContext
from manus.util import truncate_bytes

READ_CHUNK = 4096


class ShellExecTool(Tool):
    name = "shell_exec"
    description = (
        "Run a shell command (bash) inside the workspace and return combined "
        "stdout+stderr and the exit code. Long-running commands are killed at the "
        "configured timeout."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command to execute."}
        },
        "required": ["command"],
    }

    def run(self, args: dict, ctx: ToolContext) -> str:
        command = str(args.get("command", "")).strip()
        if not command:
            return "Error: shell_exec needs a non-empty command."

        cap = ctx.config.observe_cap_bytes
        deadline = time.monotonic() + ctx.config.shell_timeout_s
        timed_out = False
        capped = False
        total = 0
        chunks: list[bytes] = []

        proc = subprocess.Popen(
            ["bash", "-lc", command],
            cwd=ctx.workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # single merged pipe: two pipes can deadlock
            start_new_session=True,  # own process group, so children die with it
        )
        try:
            assert proc.stdout is not None
            fd = proc.stdout.fileno()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                readable, _, _ = select.select([fd], [], [], min(0.25, remaining))
                if readable:
                    chunk = os.read(fd, READ_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > cap:
                        capped = True
                        break
                    chunks.append(chunk)
                elif proc.poll() is not None:
                    break  # exited; drain what select still reports below
        finally:
            if proc.poll() is None:
                self._kill_group(proc)
            if proc.stdout is not None:
                proc.stdout.close()

        output = b"".join(chunks).decode("utf-8", errors="replace")
        notices = []
        if timed_out:
            notices.append(
                f"command exceeded the {ctx.config.shell_timeout_s}s timeout and was killed"
            )
        if capped:
            notices.append("output exceeded the size cap and the command was stopped")
        if not output.strip():
            body = "(no output)"
        else:
            body = truncate_bytes(output, cap)
        suffix = f"\n[{n}]" if (n := "; ".join(notices)) else ""
        return f"exit={proc.returncode}\n{body}{suffix}"

    @staticmethod
    def _kill_group(proc: subprocess.Popen) -> None:
        """Kill the whole process group so backgrounded children do not outlive us."""
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
