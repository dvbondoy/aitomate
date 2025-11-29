import os
import sys
from pathlib import Path
from typing import Any

import anyio
import mcp.types as types
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_COMMAND = sys.executable
SERVER_SCRIPT = Path(__file__).with_name("mcp_server.py")
SERVER_ARGS = [str(SERVER_SCRIPT)]
SERVER_CWD = str(SERVER_SCRIPT.parent)
SERVER_ENV = os.environ.copy()


async def _call_tool_async(name: str, arguments: dict[str, Any]):
    server_params = StdioServerParameters(
        command=SERVER_COMMAND,
        args=SERVER_ARGS,
        env=SERVER_ENV,
        cwd=SERVER_CWD,
    )
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return _normalize_result(result)


def _normalize_result(result: types.CallToolResult) -> Any:
    if result.isError:
        raise RuntimeError(f"Tool call failed: {result.model_dump()}")

    if result.structuredContent is not None:
        return result.structuredContent

    blocks: list[Any] = []
    for block in result.content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            blocks.append(block.text)
        elif block_type == "resource":
            resource = getattr(block, "resource", None)
            if resource is None:
                blocks.append(block.model_dump())
            else:
                text_value = getattr(resource, "text", None)
                blocks.append(text_value if text_value is not None else resource.model_dump())
        else:
            blocks.append(block.model_dump())

    if not blocks:
        return None

    if len(blocks) == 1:
        return blocks[0]

    return blocks


def _call_tool(name: str, arguments: dict[str, Any]):
    return anyio.run(_call_tool_async, name, arguments)


def read_file(path: str):
    return _call_tool("read_file", {"path": path})


def append_log(path: str, text: str):
    return _call_tool("append_log", {"path": path, "text": text})


def run_command(command: str, timeout: int = 30):
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    return _call_tool("run_command", {"command": command, "timeout": timeout})


def system_info():
    return _call_tool("system_info", {})


def ping_host(host: str, count: int = 4, timeout: int = 2):
    return _call_tool("ping_host", {"host": host, "count": count, "timeout": timeout})


def scan_port(host: str, port: int, timeout: float = 2.0):
    return _call_tool("scan_port", {"host": host, "port": port, "timeout": timeout})


def ssh_command(
    host: str,
    command: str,
    user: str | None = None,
    port: int = 22,
    key_path: str | None = None,
    timeout: int = 30,
):
    args: dict[str, Any] = {
        "host": host,
        "command": command,
        "port": port,
        "timeout": timeout,
    }
    if user:
        args["user"] = user
    if key_path:
        args["key_path"] = key_path
    return _call_tool("ssh_command", args)

