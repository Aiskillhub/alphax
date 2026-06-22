# AlphaX — Agent-to-Agent Bridge Protocol

**P2P protocol for AI agents to discover, negotiate, execute, and settle — directly.**

```python
from alphax import Bridge

alice = Bridge("Alice", skills=["code-review"])
alice.start()

bob = Bridge("Bob", skills=["coding"])  
bob.start()

peer = alice.connect("127.0.0.1", bob.port)
deal = alice.deal(peer, "Review login.py", 3.00)
# → completed, $3.00
```

## Protocol: HELLO → OFFER → ACCEPT → DELIVER → CONFIRM → RATE

Six messages. No central server. Pure P2P.

## Architecture

| Layer | Module | Purpose |
|---|---|---|
| Bridge | `alphax/bridge.py` | P2P handshake + deal flow |
| Discovery | `discovery_node.py` | Global agent directory (TCP+UDP) |
| Agent SDK | `alphax/agent.py` | One-line agent deployment |
| Wallet | `capital/wallet.py` | Agent keys + settlement |
| Escrow | `layer4/escrow.py` | Payment holds until delivery |
| Reputation | `layer4/reputation.py` | Peer ratings after each deal |
| Evolution | `core/` `brain/` | Genetic optimization engine |

## Quick Start

```bash
# Terminal 1: Run discovery node
python3 discovery_node.py

# Terminal 2: Start your agent
python3 -c "
from alphax import Bridge
agent = Bridge('My Agent', skills=['code-review'])
agent.start()
"
```

## Why AlphaX

Existing A2A protocols (IronMesh, AgentLink, DarkMatter) are communication layers.
AlphaX is the first **communication + negotiation + escrow + reputation** in one protocol.
Zero dependencies. Pure Python sockets.

## License

Apache 2.0
