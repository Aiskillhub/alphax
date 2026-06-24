"""AlphaX DHT — 去中心化 Agent 发现网络

不需要中心节点。Agent 之间通过 P2P 网络互相发现。

协议：
  1. JOIN    — 新 Agent 加入网络（LAN 广播 + 引导节点）
  2. GOSSIP  — 定期交换路由表
  3. QUERY   — 查询拥有某技能的 Agent
  4. ANNOUNCE — 宣告自己的技能

每个 Agent 就是一个 DHT 节点，同时也是服务提供者。
"""

from __future__ import annotations

import json
import random
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from config import config


# ── 节点信息 ──

@dataclass
class Peer:
    """DHT 网络中的一个节点"""
    node_id: str        # 唯一 ID
    host: str           # IP
    port: int           # UDP 端口
    skills: list[str]   # 提供的技能
    extra: dict = field(default_factory=dict)  # 额外信息（bridge_port等）
    last_seen: float = field(default_factory=time.time)
    reputation: float = 0.5

    def to_dict(self) -> dict:
        return {
            "id": self.node_id, "host": self.host, "port": self.port,
            "skills": self.skills, "reputation": self.reputation,
            "extra": self.extra,
        }

    @staticmethod
    def from_dict(d: dict) -> Peer:
        return Peer(
            node_id=d["id"], host=d["host"], port=d["port"],
            skills=d.get("skills", []), reputation=d.get("reputation", 0.5),
            extra=d.get("extra", {}),
        )


# ── DHT 网络 ──

class DHTNode:
    """P2P 分布式哈希表节点。

    每个 AlphaX Agent 内嵌一个 DHTNode，用于：
    - 宣告自己的技能
    - 发现拥有特定技能的其他 Agent
    - 参与网络维护（gossip）
    """

    GOSSIP_INTERVAL = 30      # gossip 间隔（秒）
    PEER_TIMEOUT = 120        # 节点超时（秒）
    MAX_PEERS = 50            # 路由表最大条目
    QUERY_TTL = 5             # 查询最大跳数

    def __init__(self, node_id: str, port: int = 0,
                 skills: list[str] | None = None,
                 bootstrap_peers: list[tuple[str, int]] | None = None):
        self.node_id = node_id
        self.skills = skills or []
        self.extra: dict = {}     # 额外元数据（bridge_port等）
        self._peers: dict[str, Peer] = {}  # node_id → Peer
        self._lock = threading.Lock()
        self._running = False

        # UDP socket
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if port:
            self._socket.bind(("0.0.0.0", port))
        self._socket.settimeout(1)
        self.port = self._socket.getsockname()[1]

        # 引导节点
        self._bootstrap = bootstrap_peers or []

        # 事件回调
        self._on_discover: Callable | None = None

    # ═══════════════════════════════════
    # 公开接口
    # ═══════════════════════════════════

    @property
    def peer_count(self) -> int:
        with self._lock:
            return len(self._peers)

    @property
    def peer_list(self) -> list[Peer]:
        with self._lock:
            return list(self._peers.values())

    def on_discover(self, callback: Callable):
        """当发现新 Agent 时回调。callback(peer: Peer)"""
        self._on_discover = callback

    def start(self):
        """启动 DHT 节点，加入网络。"""
        self._running = True

        # 1. LAN 广播：嘿，有人在吗？
        self._broadcast_hello()

        # 2. 连接引导节点
        for host, port in self._bootstrap:
            self._send_message(host, port, {
                "type": "JOIN",
                "id": self.node_id,
                "host": self._local_ip(),
                "port": self.port,
                "skills": self.skills,
                "extra": self.extra,
            })

        # 3. 后台线程
        threading.Thread(target=self._gossip_loop, daemon=True).start()
        threading.Thread(target=self._listen_loop, daemon=True).start()

        print(f"🔗 DHT Node {self.node_id[:8]}:{self.port} online")
        print(f"   Skills: {self.skills or ['(none)']}")

    def stop(self):
        self._running = False
        self._socket.close()

    def discover(self, skill: str = "", max_results: int = 10) -> list[Peer]:
        """查询拥有某技能的 Agent。skill="" 返回所有已知。"""
        with self._lock:
            if not skill:
                return sorted(
                    self.peer_list,
                    key=lambda p: p.reputation, reverse=True,
                )[:max_results]

            matched = [p for p in self._peers.values()
                       if skill.lower() in " ".join(p.skills).lower()]
            matched.sort(key=lambda p: p.reputation, reverse=True)
            result = matched[:max_results]

        # 本地没找到 → 向网络查询
        if not result:
            result = self._query_network(skill, max_results)

        return result

    def announce(self, skills: list[str]):
        """更新并宣告自己的技能。"""
        self.skills = skills
        self._broadcast_hello()

    # ═══════════════════════════════════
    # 网络协议
    # ═══════════════════════════════════

    def _listen_loop(self):
        """持续监听 UDP 消息。"""
        while self._running:
            try:
                data, addr = self._socket.recvfrom(4096)
                msg = json.loads(data.decode())
                self._handle_message(msg, addr)
            except socket.timeout:
                continue
            except Exception:
                continue

    def _handle_message(self, msg: dict, addr):
        mtype = msg.get("type", "")

        if mtype == "HELLO":
            # LAN 广播：有新节点
            peer = Peer.from_dict(msg)
            peer.extra = msg.get("extra", {})
            self._add_peer(peer)
            # 回复自己的信息
            self._send_message(addr[0], msg.get("port", addr[1]), {
                "type": "WELCOME",
                "id": self.node_id,
                "host": self._local_ip(),
                "port": self.port,
                "skills": self.skills,
                "extra": self.extra,
            })

        elif mtype == "WELCOME":
            peer = Peer.from_dict(msg)
            peer.extra = msg.get("extra", {})
            self._add_peer(peer)

        elif mtype == "JOIN":
            peer = Peer.from_dict(msg)
            peer.extra = msg.get("extra", {})
            self._add_peer(peer)
            # 回送已知节点列表
            peers_data = [p.to_dict() for p in self.peer_list[:10]]
            self._send_message(addr[0], msg.get("port", addr[1]), {
                "type": "PEERS",
                "peers": peers_data,
            })

        elif mtype == "PEERS":
            for pd in msg.get("peers", []):
                self._add_peer(Peer.from_dict(pd))

        elif mtype == "QUERY":
            skill = msg.get("skill", "")
            results = []
            with self._lock:
                for p in self._peers.values():
                    if skill.lower() in " ".join(p.skills).lower():
                        results.append(p.to_dict())
            self._send_message(addr[0], msg.get("port", addr[1]), {
                "type": "QUERY_RESULT",
                "query_id": msg.get("query_id", ""),
                "results": results[:5],
            })

        elif mtype == "QUERY_RESULT":
            # 由 _query_network 的等待线程处理
            pass

    def _gossip_loop(self):
        """定期向邻居交换路由表。"""
        while self._running:
            time.sleep(self.GOSSIP_INTERVAL)

            # 清理超时节点
            with self._lock:
                now = time.time()
                stale = [nid for nid, p in self._peers.items()
                         if now - p.last_seen > self.PEER_TIMEOUT]
                for nid in stale:
                    del self._peers[nid]

            # 随机选 3 个邻居，交换路由表
            with self._lock:
                peers = list(self._peers.values())
                random.shuffle(peers)
                targets = peers[:3]

            my_data = {
                "type": "PEERS",
                "peers": [p.to_dict() for p in self.peer_list[:10]],
            }
            for peer in targets:
                self._send_message(peer.host, peer.port, my_data)

    def _query_network(self, skill: str, max_results: int) -> list[Peer]:
        """向网络广播查询。"""
        query_id = random.randint(0, 2**31)

        msg = {
            "type": "QUERY",
            "query_id": query_id,
            "skill": skill,
            "ttl": self.QUERY_TTL,
            "port": self.port,
        }

        with self._lock:
            targets = list(self._peers.values())[:5]

        for peer in targets:
            self._send_message(peer.host, peer.port, msg)

        # 简单等待回复（生产环境应该用异步回调）
        time.sleep(2)

        with self._lock:
            matched = [p for p in self._peers.values()
                       if skill.lower() in " ".join(p.skills).lower()]
            matched.sort(key=lambda p: p.reputation, reverse=True)
            return matched[:max_results]

    # ═══════════════════════════════════
    # 内部
    # ═══════════════════════════════════

    def _broadcast_hello(self):
        """LAN 广播宣告自己。"""
        msg = {
            "type": "HELLO",
            "id": self.node_id,
            "host": self._local_ip(),
            "port": self.port,
            "skills": self.skills,
            "extra": self.extra,
        }
        data = json.dumps(msg).encode()
        try:
            self._socket.sendto(data, ("255.255.255.255", self.port))
        except Exception:
            pass

    def _add_peer(self, peer: Peer):
        with self._lock:
            existing = self._peers.get(peer.node_id)
            if existing:
                existing.last_seen = time.time()
                existing.skills = peer.skills
                return

            if len(self._peers) >= self.MAX_PEERS:
                # 移除最旧的
                oldest = min(self._peers.values(), key=lambda p: p.last_seen)
                del self._peers[oldest.node_id]

            peer.last_seen = time.time()
            self._peers[peer.node_id] = peer

            if self._on_discover:
                try:
                    self._on_discover(peer)
                except Exception:
                    pass

    def _send_message(self, host: str, port: int, msg: dict):
        try:
            data = json.dumps(msg).encode()
            self._socket.sendto(data, (host, port))
        except Exception:
            pass

    @staticmethod
    def _local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# ═══════════════════════════════════
# Demo：两个 Agent 互相发现
# ═══════════════════════════════════

if __name__ == "__main__":
    import uuid

    print("═" * 50)
    print("AlphaX DHT — 去中心化 Agent 发现")
    print("═" * 50)

    # Agent Alice：代码审查
    alice = DHTNode(
        node_id=uuid.uuid4().hex[:12],
        port=9001,
        skills=["code-review", "security-audit"],
    )
    alice.start()

    # Agent Bob：需要代码审查，启动后自动发现 Alice
    def on_found(peer: Peer):
        print(f"\n🔍 Bob 发现: {peer.node_id[:8]} → 技能: {peer.skills}")

    bob = DHTNode(
        node_id=uuid.uuid4().hex[:12],
        port=9002,
        skills=["coding", "debugging"],
        bootstrap_peers=[("127.0.0.1", 9001)],
    )
    bob.on_discover(on_found)
    bob.start()

    time.sleep(3)

    print(f"\n📊 网络状态:")
    print(f"   Alice 路由表: {alice.peer_count} peers")
    print(f"   Bob 路由表: {bob.peer_count} peers")

    print(f"\n🔍 Bob 查询 'code-review':")
    results = bob.discover("code-review")
    for p in results:
        print(f"   → {p.node_id[:8]} @ {p.host}:{p.port} [{', '.join(p.skills)}]")

    alice.stop()
    bob.stop()
    print("\n✅ Demo 完成")
