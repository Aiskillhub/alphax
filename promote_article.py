#!/usr/bin/env python3
"""
Post the AlphaX promotion article to as many free dev platforms as possible.
Platforms with open APIs are attempted programmatically.
For platforms without APIs, direct submission URLs are printed.

Usage:
    # Set env vars before running:
    export DEVTO_API_KEY="xxx"      # https://dev.to/settings/extensions
    export MEDIUM_TOKEN="xxx"       # https://medium.com/me/settings (Integration tokens)
    export HASHNODE_TOKEN="xxx"     # https://hashnode.com/settings/developer
    # Then run:
    python promote_article.py
"""

import json
import os
import sys
import urllib.request
import urllib.error

# ── Article Content ──────────────────────────────────────────────

TITLE = "Show HN: AlphaX — A2A Bridge, a P2P Protocol for AI Agents to Trade with Each Other"

BODY_MARKDOWN = """I built a P2P protocol that lets AI agents discover, negotiate, execute deals, and settle payments — without any central marketplace. Pure Python sockets, zero dependencies.

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
"""

TAGS_DEVTO = ["python", "ai", "opensource", "showdev"]
TAGS_MEDIUM = ["python", "artificial-intelligence", "open-source", "blockchain"]
TAGS_HASHNODE = ["python", "ai", "opensource"]

# ── API Clients ──────────────────────────────────────────────────

def _fetch(url, method="GET", data=None, headers=None, timeout=30):
    """Minimal HTTP client — no requests dependency needed."""
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if data:
        req.data = json.dumps(data).encode("utf-8")
        if "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return e.code, {"error": str(e), "body": body[:500]}
    except Exception as e:
        return None, {"error": str(e)}


# ── Platform Posters ─────────────────────────────────────────────

def post_devto():
    """Post to Dev.to via their public API. Requires DEVTO_API_KEY env var."""
    api_key = os.environ.get("DEVTO_API_KEY")
    if not api_key:
        return {
            "platform": "dev.to",
            "status": "SKIPPED",
            "reason": "DEVTO_API_KEY not set. Get one at https://dev.to/settings/extensions",
            "manual_url": "https://dev.to/new",  # publish manually
        }

    payload = {
        "article": {
            "title": TITLE,
            "body_markdown": BODY_MARKDOWN,
            "published": True,
            "tags": TAGS_DEVTO,
            "canonical_url": "https://github.com/Aiskillhub/alphax",
        }
    }

    status, resp = _fetch(
        "https://dev.to/api/articles",
        method="POST",
        data=payload,
        headers={"api-key": api_key},
    )

    if status == 201:
        return {
            "platform": "dev.to",
            "status": "POSTED",
            "url": resp.get("url"),
        }
    else:
        return {
            "platform": "dev.to",
            "status": "FAILED",
            "http_status": status,
            "response": resp,
            "manual_url": "https://dev.to/new",
        }


def post_medium():
    """Post to Medium via their API. Requires MEDIUM_TOKEN env var."""
    token = os.environ.get("MEDIUM_TOKEN")
    if not token:
        return {
            "platform": "medium.com",
            "status": "SKIPPED",
            "reason": "MEDIUM_TOKEN not set. Get one at https://medium.com/me/settings (Integration tokens)",
            "manual_url": "https://medium.com/new-story",
        }

    # Step 1: Get user ID
    status, me = _fetch(
        "https://api.medium.com/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status != 200:
        return {
            "platform": "medium.com",
            "status": "FAILED",
            "step": "get_user",
            "http_status": status,
            "response": me,
            "manual_url": "https://medium.com/new-story",
        }

    user_id = me.get("data", {}).get("id")
    if not user_id:
        return {
            "platform": "medium.com",
            "status": "FAILED",
            "step": "parse_user_id",
            "response": me,
            "manual_url": "https://medium.com/new-story",
        }

    # Step 2: Create post
    payload = {
        "title": TITLE,
        "contentFormat": "markdown",
        "content": BODY_MARKDOWN,
        "tags": TAGS_MEDIUM,
        "publishStatus": "public",
    }

    status, resp = _fetch(
        f"https://api.medium.com/v1/users/{user_id}/posts",
        method="POST",
        data=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    if status in (200, 201):
        return {
            "platform": "medium.com",
            "status": "POSTED",
            "url": resp.get("data", {}).get("url"),
        }
    else:
        return {
            "platform": "medium.com",
            "status": "FAILED",
            "step": "create_post",
            "http_status": status,
            "response": resp,
            "manual_url": "https://medium.com/new-story",
        }


def post_hashnode():
    """Post to Hashnode via GraphQL API. Requires HASHNODE_TOKEN env var."""
    token = os.environ.get("HASHNODE_TOKEN")
    if not token:
        return {
            "platform": "hashnode.com",
            "status": "SKIPPED",
            "reason": "HASHNODE_TOKEN not set. Get one at https://hashnode.com/settings/developer",
            "manual_url": "https://hashnode.com/create/story",
        }

    # GraphQL: first get the publication ID
    query_me = """
    query {
      me {
        publications(first: 1) {
          edges {
            node {
              id
            }
          }
        }
      }
    }
    """
    status, resp = _fetch(
        "https://gql.hashnode.com/",
        method="POST",
        data={"query": query_me},
        headers={"Authorization": f"Bearer {token}"},
    )

    if status != 200:
        return {
            "platform": "hashnode.com",
            "status": "FAILED",
            "step": "get_publication",
            "http_status": status,
            "response": resp,
            "manual_url": "https://hashnode.com/create/story",
        }

    pubs = resp.get("data", {}).get("me", {}).get("publications", {}).get("edges", [])
    if not pubs:
        return {
            "platform": "hashnode.com",
            "status": "FAILED",
            "step": "no_publication",
            "reason": "No publication found. Create one at https://hashnode.com/new/blog",
            "manual_url": "https://hashnode.com/create/story",
        }

    pub_id = pubs[0]["node"]["id"]

    # Create draft (Hashnode requires tags to be tag IDs, we'll skip tags for simplicity)
    mutation = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post {
          id
          url
          slug
        }
      }
    }
    """
    payload = {
        "query": mutation,
        "variables": {
            "input": {
                "publicationId": pub_id,
                "title": TITLE,
                "contentMarkdown": BODY_MARKDOWN,
            }
        },
    }

    status, resp = _fetch(
        "https://gql.hashnode.com/",
        method="POST",
        data=payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    if status == 200 and resp.get("data", {}).get("publishPost", {}).get("post"):
        post = resp["data"]["publishPost"]["post"]
        return {
            "platform": "hashnode.com",
            "status": "POSTED",
            "url": post.get("url"),
        }
    else:
        return {
            "platform": "hashnode.com",
            "status": "FAILED",
            "step": "create_post",
            "http_status": status,
            "response": resp,
            "manual_url": "https://hashnode.com/create/story",
        }


# ── Main ─────────────────────────────────────────────────────────

def main():
    results = []

    print("=" * 70)
    print("AlphaX Promotion — Multi-Platform Poster")
    print("=" * 70)
    print()

    # 1. Dev.to (has public API, most likely to work)
    print("[1/3] Trying Dev.to...")
    r = post_devto()
    results.append(r)
    print(f"  -> {r['status']}: {r.get('url', r.get('reason', ''))}")

    # 2. Medium
    print("[2/3] Trying Medium...")
    r = post_medium()
    results.append(r)
    print(f"  -> {r['status']}: {r.get('url', r.get('reason', ''))}")

    # 3. Hashnode
    print("[3/3] Trying Hashnode...")
    r = post_hashnode()
    results.append(r)
    print(f"  -> {r['status']}: {r.get('url', r.get('reason', ''))}")

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    posted = [r for r in results if r["status"] == "POSTED"]
    skipped = [r for r in results if r["status"] == "SKIPPED"]
    failed = [r for r in results if r["status"] == "FAILED"]

    print(f"\nPosted:  {len(posted)} platform(s)")
    for r in posted:
        print(f"  ✅ {r['platform']}: {r['url']}")

    print(f"\nSkipped (need API key): {len(skipped)} platform(s)")
    for r in skipped:
        print(f"  ⏭️  {r['platform']}: {r['reason']}")
        if "manual_url" in r:
            print(f"     Manual submit: {r['manual_url']}")

    print(f"\nFailed: {len(failed)} platform(s)")
    for r in failed:
        print(f"  ❌ {r['platform']}: {r.get('response', {}).get('error', 'unknown')}")
        if "manual_url" in r:
            print(f"     Manual submit: {r['manual_url']}")

    # Always print manual URLs for platforms without APIs
    print()
    print("=" * 70)
    print("MANUAL SUBMISSION URLs (paste the article yourself)")
    print("=" * 70)
    print()
    print("  Hacker News (Show HN): https://news.ycombinator.com/submit")
    print("    → Title:    Show HN: AlphaX — A2A Bridge, a P2P Protocol for AI Agents to Trade")
    print("    → URL:      https://github.com/Aiskillhub/alphax")
    print()
    print("  Reddit r/Python:        https://www.reddit.com/r/Python/submit")
    print("  Reddit r/programming:   https://www.reddit.com/r/programming/submit")
    print("  Reddit r/MachineLearning: https://www.reddit.com/r/MachineLearning/submit")
    print()
    print("  Lobste.rs:              https://lobste.rs/stories/new")
    print()

    return results


if __name__ == "__main__":
    main()
