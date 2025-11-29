from __future__ import annotations

import os
import platform
import shlex
import shutil
import socket
import subprocess
import time
from typing import Dict

from mcp.server import FastMCP

server = FastMCP("AITools")


def _proc_result(result: subprocess.CompletedProcess) -> Dict:
    """Structure subprocess outputs for clients."""
    status = "ok" if result.returncode == 0 else "error"
    return {
        "status": status,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


@server.tool()
def read_file(path: str) -> Dict:
    """Return the contents of a file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except FileNotFoundError:
        return {"error": "file not found", "content": ""}
    except Exception as e:
        return {"error": str(e), "content": ""}


@server.tool()
def append_log(path: str, text: str) -> Dict:
    """Append a line to a log file."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@server.tool()
def run_command(command: str, timeout: int = 30) -> Dict:
    """Execute a shell command and return stdout/stderr/returncode."""
    if not command.strip():
        return {"status": "error", "error": "command cannot be empty"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        payload = _proc_result(result)
        payload["command"] = command
        return payload
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@server.tool()
def system_info() -> Dict:
    """Return basic system information."""
    info = {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "load_avg": None,
        "uptime_seconds": None,
    }

    if hasattr(os, "getloadavg"):
        try:
            info["load_avg"] = os.getloadavg()
        except OSError:
            pass

    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_value = float(f.read().split()[0])
            info["uptime_seconds"] = round(uptime_value, 2)
    except Exception:
        # Fallback: None to signal unsupported platform (e.g., Windows)
        pass

    return info


@server.tool()
def ping_host(host: str, count: int = 4, timeout: int = 2) -> Dict:
    """Ping a host and return the raw output."""
    if not host.strip():
        return {"status": "error", "error": "host is required"}

    ping_bin = shutil.which("ping")
    if ping_bin is None:
        return {"status": "error", "error": "ping binary not available"}

    count = max(1, min(count, 10))
    timeout = max(1, timeout)

    command = [
        ping_bin,
        "-c",
        str(count),
        "-W",
        str(timeout),
        host,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=count * (timeout + 1),
        )
        payload = _proc_result(result)
        payload["command"] = " ".join(shlex.quote(part) for part in command)
        return payload
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "ping operation timed out"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@server.tool()
def scan_port(host: str, port: int, timeout: float = 2.0) -> Dict:
    """Attempt a TCP connection to determine if a port is open."""
    if not host.strip():
        return {"status": "error", "error": "host is required"}
    if not (0 < port < 65536):
        return {"status": "error", "error": "port must be between 1 and 65535"}

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(max(0.1, timeout))

    try:
        start = time.time()
        sock.connect((host, port))
        elapsed = round(time.time() - start, 4)
        return {"status": "ok", "host": host, "port": port, "open": True, "latency": elapsed}
    except (socket.timeout, ConnectionRefusedError):
        return {"status": "ok", "host": host, "port": port, "open": False}
    except Exception as e:
        return {"status": "error", "error": str(e)}
    finally:
        sock.close()


@server.tool()
def ssh_command(
    host: str,
    command: str,
    user: str | None = None,
    port: int = 22,
    key_path: str | None = None,
    timeout: int = 30,
) -> Dict:
    """Run a command over SSH using the local ssh binary."""
    if not host.strip():
        return {"status": "error", "error": "host is required"}
    if not command.strip():
        return {"status": "error", "error": "command is required"}

    ssh_bin = shutil.which("ssh")
    if ssh_bin is None:
        return {"status": "error", "error": "ssh binary not available"}

    target = f"{user}@{host}" if user else host
    ssh_cmd = [
        ssh_bin,
        "-p",
        str(port),
        "-o",
        "BatchMode=yes",
    ]

    if key_path:
        ssh_cmd.extend(["-i", key_path])

    ssh_cmd.extend([target, command])

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        payload = _proc_result(result)
        payload["command"] = " ".join(shlex.quote(part) for part in ssh_cmd)
        return payload
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"ssh command timed out after {timeout}s"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    server.run()  # FastMCP defaults to stdio transport
