## AITomate (Proof of Concept)

AITomate is a **proof-of-concept utility module** that exposes a handful of safe, structured system helpers for use by tools or agents. It focuses on simple diagnostics and remote execution, returning JSON‑style dictionaries instead of raw strings.

### Features

- **File helpers**
  - `read_file(path)` – read a text file, with basic error reporting.
  - `append_log(path, text)` – append a line to a log file.
- **Local command execution**
  - `run_command(command, timeout=30)` – run a shell command with timeout, returning `status`, `stdout`, `stderr`, and `returncode`.
- **System information**
  - `system_info()` – basic platform, CPU, load average, and uptime data.
- **Network utilities**
  - `ping_host(host, count=4, timeout=2)` – run the system `ping` binary with sane limits.
  - `scan_port(host, port, timeout=2.0)` – simple TCP connect scan with latency measurement.
- **Remote execution**
  - `ssh_command(host, command, user=None, port=22, key_path=None, timeout=30)` – run a command over `ssh` (BatchMode) if the `ssh` binary is available.

### Requirements

- **Python**: 3.10+ (standard library only; no external dependencies).
- OS: Developed and tested on Linux; some helpers rely on `/proc` and common Unix tools like `ping` and `ssh`.

### Installation

Clone the repository:

```bash
git clone https://example.com/aitomate.git
cd aitomate
```

There is no separate install step for now; you can import the module directly from the project root.

### Usage Examples

Basic usage from Python:

```python
from aitools import (
    read_file,
    run_command,
    system_info,
    ping_host,
    scan_port,
    ssh_command,
)

print(system_info())

print(run_command("echo 'hello from aitomate'"))

print(ping_host("8.8.8.8"))

print(scan_port("example.com", 22))
```

Example SSH command:

```python
res = ssh_command(
    host="my.server.local",
    user="me",
    command="uptime",
    key_path="/home/me/.ssh/id_ed25519",
)
print(res)
```

### Using `cli_agent.py`

`cli_agent.py` is an **interactive command-line assistant** that uses Ollama plus these tools.

- **1. Create `config.yaml` in the project root:**

```yaml
ollama:
  host: "http://localhost:11434"
  model: "llama3.1"
```

- **2. Make sure Ollama is running** and the model is available.

- **3. Start the CLI assistant:**

```bash
python3 cli_agent.py
```

You can then chat in the terminal; the assistant may ask to run tools like `run_command`, `ping_host`, or `ssh_command`, and will always prompt you for confirmation before executing them.

### Design Notes

- All helpers are **defensive**: they validate inputs and catch common exceptions.
- Return values are plain `dict` objects intended to be easy to serialize or pass between processes/agents.
- This is an early **proof of concept**; APIs and behavior may change as the project evolves.


