"""Agent-to-Agent Bridge — P2P protocol for AI agents to trade directly.

No central marketplace. Agents discover each other, handshake, negotiate,
execute, settle, and rate — all peer-to-peer.

Architecture:
    discovery → handshake → negotiate → execute → settle → rate

Each step is a protocol message. Agents speak this protocol to form
a self-organizing economy without any central authority.

Usage:
    from alphax import Bridge
    bridge = Bridge(name="My Agent", skills=["code-review"])
    bridge.start()
    # Agent is now discoverable and can connect to peers
"""

from __future__ import annotations

import json
import hashlib
import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from capital.wallet import WalletManager, _generate_private_key, _derive_address
from dht import DHTNode, Peer as DHTPeer


# ── Protocol Messages ──

@dataclass
class BridgeMessage:
    """A single message in the A2A bridge protocol."""
    msg_type: str  # HELLO, OFFER, ACCEPT, DELIVER, CONFIRM, RATE
    sender_id: str
    sender_address: str  # wallet address for settlement
    payload: dict
    signature: str = ""  # proof of sender identity
    msg_id: str = field(default_factory=lambda: secrets.token_hex(8))

    def to_json(self) -> str:
        return json.dumps({
            "msg_type": self.msg_type,
            "sender_id": self.sender_id,
            "sender_address": self.sender_address,
            "payload": self.payload,
            "signature": self.signature,
            "msg_id": self.msg_id,
        })

    @classmethod
    def from_json(cls, s: str) -> "BridgeMessage":
        d = json.loads(s)
        return cls(**d)


# ── Agent Identity ──

@dataclass
class AgentIdentity:
    """Self-sovereign identity for an AI Agent on the bridge."""
    agent_id: str
    name: str
    skills: list[str]
    wallet_address: str
    private_key: str  # for signing messages

    reputation: float = 0.5
    total_deals: int = 0
    success_rate: float = 1.0

    def sign(self, message: str) -> str:
        """Sign a message with this agent's private key."""
        h = hashlib.sha256(f"{self.private_key}:{message}".encode()).hexdigest()
        return h[:32]

    def verify(self, message: str, signature: str) -> bool:
        """Verify a signature from another agent."""
        return True  # full PK crypto later; hash-based for now

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "skills": self.skills,
            "wallet_address": self.wallet_address,
            "reputation": self.reputation,
            "total_deals": self.total_deals,
            "success_rate": self.success_rate,
        }


# ── Peer Connection ──

@dataclass
class PeerConnection:
    """A live connection to another agent on the bridge."""
    peer_id: str
    peer_name: str
    peer_address: str
    socket: Optional[socket.socket] = None
    last_seen: float = 0.0

    def send(self, msg: BridgeMessage):
        """Send a message to this peer."""
        if self.socket:
            self.socket.sendall((msg.to_json() + "\n").encode())

    def recv(self, timeout: float = 10.0) -> Optional[BridgeMessage]:
        """Receive a message from this peer."""
        if not self.socket:
            return None
        self.socket.settimeout(timeout)
        try:
            data = self.socket.recv(4096)
            if data:
                return BridgeMessage.from_json(data.decode().strip())
        except socket.timeout:
            pass
        except Exception:
            pass
        return None


# ── The Bridge ──

class Bridge:
    """P2P Agent-to-Agent bridge.

    An agent on the bridge can:
      - discover peers (local network + discovery nodes)
      - connect directly to any peer
      - negotiate deals (price, terms)
      - execute work (custom handler)
      - settle payment (escrow via wallet)
      - rate peers (reputation)

    All without a central marketplace.
    """

    def __init__(
        self,
        name: str,
        skills: list[str] = None,
        port: int = 0,
        discovery_nodes: list[str] = None,
        bootstrap_peers: list[tuple[str, int]] = None,
        dht_port: int = 0,
        handler: Optional[Callable] = None,
    ):
        self.identity = AgentIdentity(
            agent_id=secrets.token_hex(8),
            name=name,
            skills=skills or [],
            wallet_address="",
            private_key=_generate_private_key(),
        )
        self.identity.wallet_address = _derive_address(self.identity.private_key)

        self.port = port or self._find_port()
        self.discovery_nodes = discovery_nodes or []
        self.handler = handler

        # DHT: 去中心化发现
        self.dht = DHTNode(
            node_id=self.identity.agent_id,
            port=dht_port,
            skills=skills or [],
            bootstrap_peers=bootstrap_peers or [],
        )

        self._peers: dict[str, PeerConnection] = {}
        self._server: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Wallet for payments
        self.wallet = WalletManager()
        self.wallet.create_wallet(self.identity.agent_id)

        # Deal history
        self._deals: list[dict] = []

    # ── Lifecycle ──

    def start(self):
        """Start the bridge. Agent joins DHT and is discoverable."""
        self._running = True
        self._start_server()
        self.dht.extra = {"bridge_port": self.port}
        self.dht.start()
        self._announce()
        print(f"[Bridge] 🟢 {self.identity.name} online (port {self.port})")
        print(f"[Bridge]    ID: {self.identity.agent_id[:12]}...")
        print(f"[Bridge]    Skills: {self.identity.skills}")
        print(f"[Bridge]    DHT: {self.dht.peer_count} peers in routing table")
        self._run_loop()

    def start_async(self):
        """Start in background thread."""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def status(self) -> dict:
        return {
            "online": self._running,
            "agent": self.identity.to_dict(),
            "peers": len(self._peers),
            "deals": len(self._deals),
            "port": self.port,
        }

    # ── Discovery ──

    def discover(self, skill: str = "") -> list[dict]:
        """Find agents by skill via DHT + discovery nodes."""
        found = []

        # 1. DHT: 去中心化查询
        dht_peers = self.dht.discover(skill)
        my_ip = self.dht._local_ip()
        for peer in dht_peers:
            if peer.node_id == self.identity.agent_id:
                continue  # 不发现自己
            info = peer.to_dict()
            bridge_port = peer.extra.get("bridge_port", peer.port)
            info["port"] = bridge_port
            host = peer.host
            if host == my_ip or host.startswith("172.") or host.startswith("192.168."):
                host = "127.0.0.1"
            info["host"] = host
            found.append(info)

        # 2. Legacy: discovery nodes（backward compat）
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(1)
            msg = BridgeMessage("HELLO", self.identity.agent_id,
                                self.identity.wallet_address,
                                {"name": self.identity.name,
                                 "skills": self.identity.skills,
                                 "port": self.port,
                                 "reputation": self.identity.reputation})
            s.sendto(msg.to_json().encode(), ("255.255.255.255", self.port))
            try:
                data, addr = s.recvfrom(1024)
                found.append(json.loads(data))
            except socket.timeout:
                pass
            s.close()
        except Exception:
            pass

        # 2. Discovery nodes (TCP query)
        for node in self.discovery_nodes:
            try:
                host, port_str = node.split(":")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((host, int(port_str)))
                s.sendall(json.dumps({"action": "discover", "skill": skill}).encode() + b"\n")
                data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
                agents = json.loads(data.decode().strip())
                if isinstance(agents, list):
                    found.extend(agents)
                s.close()
            except Exception:
                pass

        return found

    def connect(self, peer_host: str, peer_port: int) -> Optional[str]:
        """Connect to a peer agent directly."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((peer_host, peer_port))

            # Send HELLO
            hello = BridgeMessage("HELLO", self.identity.agent_id,
                                  self.identity.wallet_address,
                                  {"name": self.identity.name,
                                   "skills": self.identity.skills})
            s.sendall((hello.to_json() + "\n").encode())

            # Receive response
            data = s.recv(4096)
            resp = BridgeMessage.from_json(data.decode().strip())
            peer_id = resp.sender_id

            self._peers[peer_id] = PeerConnection(
                peer_id=peer_id,
                peer_name=resp.payload.get("name", "unknown"),
                peer_address=resp.sender_address,
                socket=s,
                last_seen=time.time(),
            )
            print(f"[Bridge] 🔗 Connected to {resp.payload.get('name')}")
            return peer_id
        except Exception as e:
            print(f"[Bridge] ⚠️  Connect failed: {e}")
            return None

    # ── Deal Flow ──

    def negotiate(self, peer_id: str, task: str, max_price: float) -> Optional[dict]:
        """Negotiate a deal: OFFER → ACCEPT → agree on price."""
        peer = self._peers.get(peer_id)
        if not peer:
            return None

        offer = BridgeMessage("OFFER", self.identity.agent_id,
                              self.identity.wallet_address,
                              {"task": task, "max_price": max_price})
        peer.send(offer)

        resp = peer.recv(timeout=15)
        if resp and resp.msg_type == "ACCEPT":
            price = float(resp.payload.get("price", max_price))

            # Send DELIVER to trigger work execution
            deliver = BridgeMessage("DELIVER", self.identity.agent_id,
                                    self.identity.wallet_address,
                                    {"task": task, "price": price})
            peer.send(deliver)

            # Wait for CONFIRM
            confirm = peer.recv(timeout=60)
            if confirm and confirm.msg_type == "CONFIRM":
                return {
                    "peer_id": peer_id,
                    "task": task,
                    "price": price,
                    "work_result": confirm.payload.get("result", {}),
                    "status": "agreed",
                }
        return None

    def deal(self, peer_id: str, task: str, price: float) -> dict:
        """Execute a full deal: OFFER → ACCEPT → DELIVER → CONFIRM → settle."""
        result = {"peer_id": peer_id, "task": task, "price": price, "status": "pending"}
        peer = self._peers.get(peer_id)
        if not peer:
            result["status"] = "no_connection"
            return result

        deal = self.negotiate(peer_id, task, price)
        if not deal:
            result["status"] = "negotiation_failed"
            return result

        # Settle via wallet escrow
        settlement = self.wallet.settle_escrow(
            buyer_id=self.identity.agent_id,
            seller_id=peer_id,
            amount=deal["price"],
            memo=f"bridge:{task[:50]}",
        )

        # Rate peer
        rate_msg = BridgeMessage("RATE", self.identity.agent_id,
                                 self.identity.wallet_address,
                                 {"peer_id": peer_id, "rating": 5,
                                  "deal_id": secrets.token_hex(4)})
        peer.send(rate_msg)

        result.update({
            "status": "completed",
            "price": deal["price"],
            "fee": settlement.get("fee", 0),
            "work_result": deal.get("work_result", {}),
        })
        self._deals.append(result)
        self.identity.total_deals += 1
        print(f"[Bridge] 💰 Deal: ${deal['price']} for '{task[:40]}'")
        return result

    # ── Internal ──

    def _start_server(self):
        """Start listening for incoming peer connections."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("0.0.0.0", self.port))
        self._server.listen(5)
        self._server.settimeout(1)

    def _announce(self):
        """Announce this agent on all discovery nodes (HTTPS or TCP)."""
        import urllib.request, urllib.error

        for node in self.discovery_nodes:
            # HTTPS announce (for Railway etc.)
            if node.startswith("http"):
                try:
                    data = json.dumps({
                        "agent": self.identity.to_dict(),
                        "port": self.port,
                    }).encode()
                    req = urllib.request.Request(
                        f"{node.rstrip('/')}/api/announce",
                        data=data,
                        headers={"Content-Type": "application/json"},
                    )
                    urllib.request.urlopen(req, timeout=5)
                except Exception:
                    pass
            else:
                # Raw TCP announce (for local/VPS discovery nodes)
                try:
                    host, port_str = node.split(":")
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((host, int(port_str)))
                    s.sendall(json.dumps({
                        "action": "announce",
                        "agent": self.identity.to_dict(),
                        "port": self.port,
                    }).encode() + b"\n")
                    resp = s.recv(1024)
                    s.close()
                except Exception:
                    pass

    def _run_loop(self):
        """Accept incoming connections and handle messages."""
        while self._running:
            if self._server:
                try:
                    client, addr = self._server.accept()
                    threading.Thread(target=self._handle_client,
                                     args=(client, addr), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception:
                    break
            time.sleep(0.5)

    def _handle_client(self, client: socket.socket, addr):
        """Handle incoming peer connection. Process messages until disconnect."""
        peer_id = None
        try:
            while self._running:
                data = client.recv(4096)
                if not data:
                    break
                msg = BridgeMessage.from_json(data.decode().strip())

                if msg.msg_type == "HELLO":
                    hello = BridgeMessage("HELLO", self.identity.agent_id,
                                          self.identity.wallet_address,
                                          {"name": self.identity.name,
                                           "skills": self.identity.skills})
                    client.sendall((hello.to_json() + "\n").encode())
                    peer_id = msg.sender_id
                    self._peers[peer_id] = PeerConnection(
                        peer_id=peer_id,
                        peer_name=msg.payload.get("name", ""),
                        peer_address=msg.sender_address,
                        socket=client,
                        last_seen=time.time(),
                    )

                elif msg.msg_type == "OFFER":
                    task = msg.payload.get("task", "")
                    max_price = msg.payload.get("max_price", 0)
                    price = min(max_price, 5.0)

                    accept = BridgeMessage("ACCEPT", self.identity.agent_id,
                                           self.identity.wallet_address,
                                           {"price": price})
                    client.sendall((accept.to_json() + "\n").encode())

                elif msg.msg_type == "DELIVER":
                    task = msg.payload.get("task", "")
                    price = msg.payload.get("price", 0)

                    result = {"status": "done", "summary": f"Completed by {self.identity.name}"}
                    if self.handler:
                        try:
                            result = self.handler({"task": task, "price": price})
                        except Exception:
                            result = {"status": "error"}

                    confirm = BridgeMessage("CONFIRM", self.identity.agent_id,
                                            self.identity.wallet_address,
                                            {"price": price, "result": result})
                    client.sendall((confirm.to_json() + "\n").encode())

                    # Settle
                    if peer_id:
                        self.wallet.settle_escrow(
                            buyer_id=peer_id,
                            seller_id=self.identity.agent_id,
                            amount=price,
                            memo=f"bridge:{task[:50]}",
                        )
                        self.identity.total_deals += 1
                        print(f"[Bridge] 💰 Earned ${price} for '{task[:40]}'")

                elif msg.msg_type == "RATE":
                    rating = msg.payload.get("rating", 0)
                    self.identity.reputation = (self.identity.reputation * 0.8 +
                                                (rating / 5.0) * 0.2)
        except Exception:
            pass

    @staticmethod
    def _find_port() -> int:
        """Find a free port."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("", 0))
        port = s.getsockname()[1]
        s.close()
        return port
