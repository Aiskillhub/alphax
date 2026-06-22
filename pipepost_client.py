#!/usr/bin/env python3
"""
MCP client to interact with Pipepost MCP server for publishing.
Communicates via stdio with the pipepost-mcp node process.

Usage:
    echo '{"platform":"devto","key":"your-devto-api-key"}' | python3 pipepost_client.py setup
    cat PROMO_ARTICLE.md | python3 pipepost_client.py publish devto
"""

import json
import subprocess
import sys
import os

PIPEPOST_SCRIPT = os.path.expanduser(
    "~/.npm-cache-new/_npx/0834f30e00b743af/node_modules/pipepost-mcp/dist/index.js"
)


def mcp_request(proc, method, params=None, request_id=1):
    """Send a JSON-RPC request and read the response."""
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    req = json.dumps(payload) + "\n"
    try:
        proc.stdin.write(req)
        proc.stdin.flush()
    except (BrokenPipeError, OSError):
        return None
    line = proc.stdout.readline()
    if not line:
        return None
    return json.loads(line)


def main():
    if len(sys.argv) < 2:
        print("Usage: pipepost_client.py <setup|publish|status> [args]")
        sys.exit(1)

    cmd = sys.argv[1]

    # Start the pipepost process
    proc = subprocess.Popen(
        ["node", PIPEPOST_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Initialize
    init_resp = mcp_request(proc, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "promote", "version": "1.0"},
    })
    if not init_resp:
        print("Failed to initialize pipepost MCP server")
        stderr = proc.stderr.read()
        if stderr:
            print("STDERR:", stderr)
        proc.kill()
        sys.exit(1)

    # Send initialized notification
    proc.stdin.write(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
    )
    proc.stdin.flush()

    if cmd == "status":
        resp = mcp_request(proc, "tools/call", {
            "name": "status",
            "arguments": {},
        }, request_id=2)
        if resp and "result" in resp:
            content = resp["result"].get("content", [{}])[0].get("text", "{}")
            try:
                print(json.dumps(json.loads(content), indent=2))
            except (json.JSONDecodeError, TypeError):
                print(content)
        else:
            print("status failed:", resp)

    elif cmd == "setup":
        # Read JSON from stdin: {"platform": "devto", "api_key": "xxx"}
        config = json.loads(sys.stdin.read())
        platform = config["platform"]
        credentials = {k: v for k, v in config.items() if k != "platform"}

        resp = mcp_request(proc, "tools/call", {
            "name": "setup",
            "arguments": {
                "platform": platform,
                "credentials": credentials,
            },
        }, request_id=2)
        if resp and "result" in resp:
            content = resp["result"].get("content", [{}])[0].get("text", "{}")
            print(json.dumps(json.loads(content), indent=2))
        else:
            print("setup failed:", resp)

    elif cmd == "publish":
        if len(sys.argv) < 3:
            print("Usage: pipepost_client.py publish <platform>")
            proc.kill()
            sys.exit(1)
        platform = sys.argv[2]
        content = sys.stdin.read().strip()

        # Parse title from first # heading
        title = "AlphaX — A2A Bridge"
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        resp = mcp_request(proc, "tools/call", {
            "name": "publish",
            "arguments": {
                "platform": platform,
                "title": title,
                "content": content,
                "tags": ["python", "ai", "opensource", "showdev"],
                "status": "published",
            },
        }, request_id=2)
        if resp and "result" in resp:
            content_text = resp["result"].get("content", [{}])[0].get("text", "{}")
            print(json.dumps(json.loads(content_text), indent=2))
        else:
            print("publish failed:", resp)
            stderr = proc.stderr.read()
            if stderr:
                print("STDERR:", stderr)

    else:
        print(f"Unknown command: {cmd}")

    proc.stdin.close()
    proc.wait(timeout=5)


if __name__ == "__main__":
    main()
