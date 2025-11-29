#!/usr/bin/env python3
"""Interactive CLI assistant that uses Ollama + MCP tools."""

from __future__ import annotations

import json
from typing import Any
from pathlib import Path
from dataclasses import dataclass
import itertools
import sys
import threading
import time

import yaml
from ollama import Client

from mcp_client import (
    append_log,
    ping_host,
    read_file,
    run_command,
    scan_port,
    ssh_command,
    system_info,
)

CONFIG_PATH = Path("config.yaml")

if not CONFIG_PATH.exists():
    raise SystemExit("Missing config.yaml. Please create one before running cli_agent.py.")

config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

OLLAMA_HOST = config["ollama"]["host"]
OLLAMA_MODEL = config["ollama"]["model"]

ollama_client = Client(host=OLLAMA_HOST)

SYSTEM_PROMPT = """
You are a helpful command-line automation assistant.

You can call tools by replying with JSON in the following shape:
{ "tool": "<tool_name>", "args": { ... } }

Available tools:
- read_file(path: str)
- append_log(path: str, text: str)
- run_command(command: str, timeout: int = 30)
- system_info()
- ping_host(host: str, count: int = 4, timeout: int = 2)
- scan_port(host: str, port: int, timeout: float = 2.0)
- ssh_command(host: str, command: str, user?: str, port: int = 22, key_path?: str, timeout: int = 30)

When you reach a conclusion, respond with JSON:
{ "final": "<your summary or answer>" }

For short, conversational replies that don't require tool usage, respond with plain text.
"""

TOOL_MAP = {
    "read_file": read_file,
    "append_log": append_log,
    "run_command": run_command,
    "system_info": system_info,
    "ping_host": ping_host,
    "scan_port": scan_port,
    "ssh_command": ssh_command,
}


def ask_ollama(messages: list[dict[str, str]]) -> str:
    response = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=messages,
    )
    return response["message"]["content"]


def _pretty(obj: object) -> str:
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except TypeError:
        return str(obj)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Find the first JSON object within arbitrary text."""
    start = text.find("{")

    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)

    return None


@dataclass
class SpinnerHandle:
    stop_event: threading.Event
    message: str
    thread: threading.Thread


def _start_spinner(message: str = "assistant is thinking") -> SpinnerHandle:
    stop_event = threading.Event()

    def run():
        for symbol in itertools.cycle("|/-\\"):
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r{message} {symbol}")
            sys.stdout.flush()
            time.sleep(0.15)
        sys.stdout.write("\r")
        sys.stdout.flush()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return SpinnerHandle(stop_event=stop_event, message=message, thread=thread)


def _stop_spinner(handle: SpinnerHandle | None) -> None:
    if handle is None:
        return
    handle.stop_event.set()
    handle.thread.join()
    sys.stdout.write("\r" + " " * (len(handle.message) + 2) + "\r")
    sys.stdout.flush()


def _confirm_tool(tool_name: str, args: dict[str, Any]) -> bool:
    # Try to show the *actual* command that will be executed, when possible.
    preview: str | None = None

    if tool_name == "run_command":
        cmd = args.get("command")
        if isinstance(cmd, str) and cmd.strip():
            preview = cmd
    elif tool_name == "ping_host":
        host = str(args.get("host", "")).strip()
        if host:
            count = int(args.get("count", 4) or 4)
            timeout = int(args.get("timeout", 2) or 2)
            preview = f"ping -c {count} -W {timeout} {host}"
    elif tool_name == "ssh_command":
        host = str(args.get("host", "")).strip()
        command = str(args.get("command", "")).strip()
        if host and command:
            user = str(args.get("user", "")).strip()
            port = int(args.get("port", 22) or 22)
            key_path = str(args.get("key_path", "")).strip()
            target = f"{user}@{host}" if user else host
            parts = ["ssh", "-p", str(port), "-o", "BatchMode=yes"]
            if key_path:
                parts.extend(["-i", key_path])
            parts.extend([target, command])
            preview = " ".join(parts)

    if preview:
        prompt = f"Execute: {preview}? [y/N]: "
    else:
        prompt = f"Execute tool '{tool_name}' with args {_pretty(args)}? [y/N]: "
    while True:
        choice = input(prompt).strip().lower()
        if choice in {"y", "yes"}:
            return True
        if choice in {"n", "no", ""}:
            return False
        print("Please answer 'y' or 'n'.")


def process_assistant(messages: list[dict[str, str]]) -> None:
    """Run the assistant until it emits a non-tool response."""
    while True:
        spinner = _start_spinner()
        try:
            reply = ask_ollama(messages)
        finally:
            _stop_spinner(spinner)
        assistant_logged = False
        try:
            data = json.loads(reply)
        except json.JSONDecodeError:
            data = _extract_json_object(reply)
            if data is None:
                print(f"assistant> {reply}")
                messages.append({"role": "assistant", "content": reply})
                break
            print(f"assistant> {reply}")
            messages.append({"role": "assistant", "content": reply})
            assistant_logged = True

        if isinstance(data, dict) and "tool" in data:
            tool_name = data["tool"]
            args = data.get("args", {}) or {}
            func = TOOL_MAP.get(tool_name)
            if not assistant_logged:
                messages.append({"role": "assistant", "content": reply})

            if func is None:
                error_message = f"Unknown tool '{tool_name}'."
                print(f"assistant> {error_message}")
                messages.append({"role": "user", "content": error_message})
                break

            if not _confirm_tool(tool_name, args):
                decline_msg = f"User declined to run tool {tool_name}."
                print(f"assistant> {decline_msg}")
                messages.append({"role": "user", "content": decline_msg})
                break

            try:
                result = func(**args)
            except Exception as exc:
                result = {"status": "error", "error": str(exc)}

            # For human output, prefer showing just stdout when available.
            display = None
            if isinstance(result, dict):
                if "stdout" in result and isinstance(result["stdout"], str):
                    display = result["stdout"]
                elif "result" in result and isinstance(result["result"], dict):
                    inner = result["result"]
                    if "stdout" in inner and isinstance(inner["stdout"], str):
                        display = inner["stdout"]

            if display is None:
                display = _pretty(result)

            print(f"[tool:{tool_name}] {display}")
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool {tool_name} result: {json.dumps(result, ensure_ascii=False)}",
                }
            )

            # Loop to allow the assistant to react to the tool output.
            continue

        if isinstance(data, dict) and "final" in data:
            final_message = data["final"]
            if not assistant_logged:
                print(f"assistant> {final_message}")
            messages.append({"role": "assistant", "content": final_message})
            break

        # Fallback for structured but non-tool, non-final JSON
        print(f"assistant> {reply}")
        messages.append({"role": "assistant", "content": reply})
        break


def main():
    print("Interactive automation chat. Type 'exit' to quit.")
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT.strip()}]

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break

        messages.append({"role": "user", "content": user_input})
        process_assistant(messages)


if __name__ == "__main__":
    main()

