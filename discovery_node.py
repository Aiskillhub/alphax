"""Discovery Node — thin registry for A2A Bridge agents.

Agents announce themselves, query for peers by skill, then connect directly.
Discovery node never touches money or transactions. Just an address book.

Run:
    python3 discovery_node.py              # default port 9999
    python3 discovery_node.py --port 8888  # custom port
"""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field


@dataclass
class AgentEntry:
    agent_id: str
    name: str
    skills: list[str]
    host: str       # IP address
    port: int       # Bridge port
    wallet: str = ""
    reputation: float = 0.5
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "skills": self.skills,
            "host": self.host,
            "port": self.port,
            "wallet": self.wallet,
            "reputation": self.reputation,
        }


class DiscoveryNode:
    """A lightweight registry for Agent discovery."""

    def __init__(self, port: int = 9999):
        self.port = port
        self._agents: dict[str, AgentEntry] = {}
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        self._running = True
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp.bind(("0.0.0.0", self.port))
        tcp.listen(50)
        tcp.settimeout(1)

        # Also listen for UDP broadcast announcements
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.bind(("0.0.0.0", self.port))
        udp.settimeout(1)

        print(f"🔍 Discovery Node running on port {self.port}")
        print(f"   TCP: agents connect here to announce & query")
        print(f"   UDP: broadcast announcements")
        print()

        # Cleanup stale agents periodically
        def cleanup():
            while self._running:
                time.sleep(60)
                self._cleanup()

        threading.Thread(target=cleanup, daemon=True).start()

        while self._running:
            try:
                client, addr = tcp.accept()
                threading.Thread(target=self._handle_tcp, args=(client, addr),
                                 daemon=True).start()
            except socket.timeout:
                pass

            try:
                data, addr = udp.recvfrom(2048)
                self._handle_udp(data, addr)
            except socket.timeout:
                pass

    def _handle_tcp(self, client: socket.socket, addr):
        try:
            data = client.recv(4096)
            if not data:
                return

            request = json.loads(data.decode().strip())
            action = request.get("action", "")

            if action == "announce":
                agent = request.get("agent", {})
                entry = AgentEntry(
                    agent_id=agent.get("agent_id", ""),
                    name=agent.get("name", ""),
                    skills=agent.get("skills", []),
                    host=addr[0],
                    port=request.get("port", 0),
                    wallet=agent.get("wallet_address", ""),
                    reputation=agent.get("reputation", 0.5),
                )
                with self._lock:
                    self._agents[entry.agent_id] = entry
                client.sendall(json.dumps({"status": "registered"}).encode() + b"\n")

            elif action == "discover":
                skill = request.get("skill", "")
                results = []
                with self._lock:
                    for agent in self._agents.values():
                        if not skill or skill in agent.skills:
                            results.append(agent.to_dict())
                # Sort by reputation
                results.sort(key=lambda a: a["reputation"], reverse=True)
                client.sendall(json.dumps(results).encode() + b"\n")

            elif action == "list":
                with self._lock:
                    results = [a.to_dict() for a in self._agents.values()]
                client.sendall(json.dumps(results).encode() + b"\n")

        except Exception as e:
            pass
        finally:
            client.close()

    def _handle_udp(self, data: bytes, addr):
        try:
            msg = json.loads(data.decode().strip())
            if msg.get("msg_type") == "HELLO":
                # Someone is broadcasting their presence on LAN
                payload = msg.get("payload", {})
                entry = AgentEntry(
                    agent_id=msg.get("sender_id", ""),
                    name=payload.get("name", ""),
                    skills=payload.get("skills", []),
                    host=addr[0],
                    port=payload.get("port", 0),
                )
                with self._lock:
                    self._agents[entry.agent_id] = entry
        except Exception:
            pass

    def _cleanup(self):
        now = time.time()
        with self._lock:
            stale = [aid for aid, a in self._agents.items()
                     if now - a.last_seen > 300]  # 5 min timeout
            for aid in stale:
                del self._agents[aid]
            if stale:
                print(f"  Cleaned {len(stale)} stale agents ({len(self._agents)} active)")

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_agents": len(self._agents),
                "skills": list(set(s for a in self._agents.values() for s in a.skills)),
                "agents": [a.to_dict() for a in list(self._agents.values())[:10]],
            }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="A2A Bridge Discovery Node")
    parser.add_argument("--port", type=int, default=9999)
    args = parser.parse_args()

    node = DiscoveryNode(port=args.port)
    try:
        node.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
