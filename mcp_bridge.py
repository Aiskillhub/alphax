"""AlphaX MCP Bridge — Claude Code 可用的 Agent 交易工具

将 AlphaX Bridge 暴露为 MCP Server，任何支持 MCP 的 Agent（Claude Code 等）
都可以发现、连接、雇佣网络上的其他 Agent。

用法：
  # 在 Claude Code 中配置 MCP server
  # ~/.claude/claude_desktop_config.json 或项目 .mcp.json:
  {
    "mcpServers": {
      "alphax-bridge": {
        "command": "python3",
        "args": ["mcp_bridge.py", "--port", "9101"]
      }
    }
  }

  # 然后 Claude Code Agent 就可以：
  # - bridge_discover("code-review")  → 找到审查 Agent
  # - bridge_deal(peer_id, task, price) → 雇佣它
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from alphax.bridge import Bridge


# ═══════════════════════════════════════
# MCP Server Protocol (JSON-RPC 2.0 over stdio)
# ═══════════════════════════════════════

class MCPServer:
    """Minimal MCP server that wraps AlphaX Bridge as tools."""

    def __init__(self, name: str = "AlphaX Bridge Agent",
                 skills: list[str] = None, port: int = 9101):
        self.bridge = Bridge(name=name, skills=skills or ["code-review", "web_tool_builder"], port=port)
        self.bridge.start_async()
        self._tools = self._register_tools()

    def _register_tools(self) -> list[dict]:
        """定义 MCP 工具列表。"""
        return [
            {
                "name": "bridge_discover",
                "description": "Discover AI agents on the P2P network by skill. Returns agents that can provide a service.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "description": "Skill to search for (e.g., 'code-review', 'web_tool_builder', 'security-audit')"
                        }
                    },
                    "required": ["skill"]
                }
            },
            {
                "name": "bridge_connect",
                "description": "Connect directly to a discovered peer agent for P2P communication.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "host": {"type": "string", "description": "Peer host/IP"},
                        "port": {"type": "integer", "description": "Peer bridge port"}
                    },
                    "required": ["host", "port"]
                }
            },
            {
                "name": "bridge_deal",
                "description": "Negotiate and execute a deal with a connected peer. Full flow: OFFER→ACCEPT→DELIVER→CONFIRM→SETTLE.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "peer_id": {"type": "string", "description": "Connected peer ID"},
                        "task": {"type": "string", "description": "Task description"},
                        "price": {"type": "number", "description": "Price in USD"}
                    },
                    "required": ["peer_id", "task", "price"]
                }
            },
            {
                "name": "bridge_status",
                "description": "Get current agent status: peers connected, deals completed, earnings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
        ]

    def handle_request(self, request: dict) -> dict:
        """处理 MCP JSON-RPC 请求。"""
        method = request.get("method", "")
        req_id = request.get("id", 0)
        params = request.get("params", {})

        # ── Initialize ──
        if method == "initialize":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "alphax-bridge",
                        "version": "1.0.0",
                    },
                    "capabilities": {"tools": {}},
                }
            }

        # ── List Tools ──
        if method == "tools/list":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"tools": self._tools},
            }

        # ── Call Tool ──
        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = self._call_tool(tool_name, tool_args)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
                },
            }

        # ── Notifications (no response needed) ──
        if method == "notifications/initialized" or method.startswith("notifications/"):
            return None

        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    def _call_tool(self, name: str, args: dict) -> dict:
        """执行 Bridge 工具。"""
        if name == "bridge_discover":
            skill = args.get("skill", "")
            agents = self.bridge.discover(skill)
            return {"agents": agents, "count": len(agents)}

        elif name == "bridge_connect":
            host = args.get("host", "")
            port = args.get("port", 0)
            peer_id = self.bridge.connect(host, port)
            return {"connected": peer_id is not None, "peer_id": peer_id or ""}

        elif name == "bridge_deal":
            peer_id = args.get("peer_id", "")
            task = args.get("task", "")
            price = args.get("price", 0)
            deal = self.bridge.deal(peer_id, task, price)
            return deal

        elif name == "bridge_status":
            return self.bridge.status()

        return {"error": f"Unknown tool: {name}"}

    def run(self):
        """MCP 主循环：读 stdin → 处理 → 写 stdout。"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response:
                    sys.stdout.write(json.dumps(response) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err = {"jsonrpc": "2.0", "id": request.get("id", 0) if request else 0,
                       "error": {"code": -32603, "message": str(e)}}
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AlphaX MCP Bridge Server")
    parser.add_argument("--port", type=int, default=9101)
    parser.add_argument("--name", default="AlphaX Bridge Agent")
    parser.add_argument("--skills", default="code-review,web_tool_builder")
    args = parser.parse_args()

    skills = [s.strip() for s in args.skills.split(",")]
    server = MCPServer(name=args.name, skills=skills, port=args.port)
    server.run()
