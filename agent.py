# agent.py
import json
import yaml
import time
from ollama import Client
from mcp_client import read_file, append_log

# Load config
config = yaml.safe_load(open("config.yaml"))

OLLAMA_HOST = config["ollama"]["host"]
OLLAMA_MODEL = config["ollama"]["model"]
AUTH_LOG = config["logs"]["auth"]
THREAT_LOG = config["logs"]["threat"]

SYSTEM_PROMPT = f"""
You are an autonomous agent for log monitoring.

Tools available:

1) read_file:
   {{ "tool": "read_file", "args": {{"path": "<filepath>"}} }}

2) append_log:
   {{ "tool": "append_log", "args": {{"path": "<filepath>", "text": "<text>"}} }}

Rules:
- Use read_file to inspect logs.
- Use append_log to write findings.
- When finished, output ONLY:
  {{ "final": "<summary>" }}
"""

ollama_client = Client(host=OLLAMA_HOST)


def ask_ollama(prompt: str) -> str:
    res = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return res["message"]["content"]

def run_agent():
    task = f"Analyze {AUTH_LOG} for suspicious activity and write notes to {THREAT_LOG}."

    while True:
        print("\n📡 Asking LLM...\n")
        reply = ask_ollama(task)
        print("LLM Reply:\n", reply)

        try:
            data = json.loads(reply)

            # Tool call
            if "tool" in data:
                tool_name = data["tool"]
                args = data.get("args", {})

                if tool_name == "read_file":
                    result = read_file(args["path"])
                    print("Tool result:", result)
                    task = f"Tool result: {result}. Continue."
                    continue

                elif tool_name == "append_log":
                    result = append_log(args["path"], args["text"])
                    print("Logged:", result)
                    task = f"Logged: {result}. Continue."
                    continue

            elif "final" in data:
                print("\n===== FINAL AGENT SUMMARY =====\n")
                print(data["final"])
                break

        except Exception:
            # Treat non-JSON reply as final output
            print("\n===== FINAL RAW OUTPUT =====\n")
            print(reply)
            break

        time.sleep(2)

if __name__ == "__main__":
    run_agent()

