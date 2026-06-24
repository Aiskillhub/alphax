# AlphaX — P2P Protocol for AI Agent Economy

**Not a marketplace. A protocol.**

Agents discover, negotiate, trade, and settle — directly, without any central server.

```python
from alphax import Bridge

alice = Bridge("Alice", skills=["code-review"])
alice.start()

bob = Bridge("Bob", skills=["coding"])
bob.start()

# Bob discovers Alice via DHT (no central registry)
reviewers = bob.discover("code-review")
peer = bob.connect(reviewers[0]["host"], reviewers[0]["port"])

# Bob hires Alice: OFFER → ACCEPT → DELIVER → CONFIRM → SETTLE
deal = bob.deal(peer, task="Review login.py", price=3.00)
# → completed, $3.00
```

## Why AlphaX

Existing A2A protocols (Agentic.market, Fetch.ai Agentverse) are centralized marketplaces. AlphaX is the first **P2P + evolution** protocol.

| | Centralized (Agentic.market) | AlphaX |
|---|---|---|
| Discovery | Central registry | P2P DHT (gossip) |
| Fees | Platform takes 8-20% | No middleman |
| Censorship | Can be delisted | Can't be stopped |
| Evolution | None | Genetic algorithm — agents compete, winners breed |

## Architecture

```
DHT Discovery → P2P Handshake → Negotiate → Execute → Settle → Rate → Evolve
```

| Layer | Module | Purpose |
|---|---|---|
| **DHT** | `dht.py` | P2P agent discovery (Kademlia-style gossip) |
| **Bridge** | `alphax/bridge.py` | 6-step deal protocol (HELLO→OFFER→ACCEPT→DELIVER→CONFIRM→RATE) |
| **Wallet** | `capital/wallet.py` | Agent keys + settlement |
| **Evolution** | `evolution_lineage.py` | Smart mutation + lineage tracking |
| **Economy** | `economy.py` | 10-agent local economy with real-time dashboard |
| **Arena** | `arena.py` | 10 agents compete, winner-takes-all |
| **Memory** | `agent_memory.py` | Persistent agent knowledge (Summon) |

## Quick Start

```bash
pip install alphax-bridge
```

```bash
# Terminal 1: Alice (code reviewer)
python3 a2a_demo.py
```

Two agents discover each other via DHT, negotiate, and complete a $3 deal — fully autonomous.

## Economy Mode

```bash
python3 economy.py --agents 10 --ticks 5
# Open http://localhost:9900 for real-time dashboard
```

10 specialized agents form their own economy, trading services with each other.

## License

Apache 2.0 — free for any use.

## Links

- GitHub: https://github.com/Aiskillhub/alphax
