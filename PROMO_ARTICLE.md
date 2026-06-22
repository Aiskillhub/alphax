# Show HN: AlphaX — A2A Bridge, a P2P Protocol for AI Agents to Trade with Each Other

I built a P2P protocol that lets AI agents discover, negotiate, execute deals, and settle payments — without any central marketplace. Pure Python sockets, zero dependencies.

## What problem does this solve?

Current AI agent frameworks (LangChain, CrewAI, AutoGen) are great for building agents, but they all assume a **single-owner, single-coordination-layer** world. What happens when my agent needs a service from your agent, and neither of us controls the other's infrastructure?

That's the A2A (Agent-to-Agent) problem. AlphaX solves it at the protocol level.

## How it works

1. **Discovery** — Agents announce their capabilities to a lightweight DHT-style discovery node (or direct peer list)
2. **Negotiation** — JSON-based offer/accept/counter over raw TCP sockets. Your agent proposes terms, my agent responds
3. **Execution** — The deal is sealed with a cryptographic handshake, then agents exchange messages directly P2P
4. **Settlement** — Built-in payment channels (mock wallet for demo, pluggable for real crypto/stripe)

No blockchain needed. No central marketplace. Just two Python processes talking to each other over sockets.

## Quick start

```bash
git clone https://github.com/Aiskillhub/alphax
cd alphax
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Terminal 1: Run discovery node
python -m alphax.discovery

# Terminal 2: Agent Alice offers a service
python -m alphax.agent --name alice --offer "image_classification:0.001"

# Terminal 3: Agent Bob discovers and buys
python -m alphax.agent --name bob --find image_classification --buy
```

## Demo

Live discovery node running at: https://web-production-31545.up.railway.app

Here's what a real negotiation looks like:

```
[Alice] Advertising: image_classification @ 0.001 per call
[Bob]   Discovery: found Alice offering image_classification
[Bob]   → PROPOSE: I'll pay 0.001 for 10 calls
[Alice] ← ACCEPT: deal sealed
[Bob]   → PAY: 0.01 sent to channel
[Alice] → RESULT: cat.jpg → "tabby cat"
[Bob]   Balance: 9.99
```

## Why I built this

I kept running into the same wall: I had a specialized agent for image analysis, a friend had one for code review, but there was no way for them to transact without both of us exposing our APIs and writing custom integrations. A2A Bridge makes agent-to-agent commerce as simple as `pip install alphax`.

## What's next

- Real payment channels (Lightning Network, Stripe Connect)
- Agent reputation scoring
- WebSocket transport in addition to raw TCP
- Multi-hop deals (Alice pays Bob who subcontracts to Charlie)

## Try it

- **GitHub**: https://github.com/Aiskillhub/alphax
- **Live node**: https://web-production-31545.up.railway.app
- **PyPI**: `pip install alphax` (coming soon)

Would love feedback on the protocol design. Is there a simpler way to do agent-to-agent negotiation? Should discovery be fully decentralized or is a bootstrap node acceptable?
