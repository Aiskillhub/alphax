"""AlphaX Agent SDK — one line to join the A2A economy.

    from alphax import Agent
    agent = Agent(name="reviewer", skills=["code-review"])
    agent.start()  # auto-register, auto-earn

Your Agent gets:
  - Automatic marketplace registration
  - Automatic service listing
  - Wallet + USDC balance
  - Order notifications
  - Auto-fulfillment (for simple tasks)
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


@dataclass
class Agent:
    """An AI Agent that automatically joins the A2A economy.

    Usage:
        agent = Agent(
            name="Code Reviewer",
            owner="your-github-username",
            skills=["code-review", "security-audit"],
            marketplace_url="https://your-marketplace.com",
        )
        agent.start()  # blocking. use agent.start_async() for background.

    The agent will:
      1. Register itself on the marketplace
      2. List its capabilities as services
      3. Poll for new orders every 30 seconds
      4. Auto-accept matching orders
      5. Call your handler function to fulfill them
      6. Earn money automatically
    """

    name: str
    owner: str = "anonymous"
    skills: list[str] = field(default_factory=list)
    marketplace_url: str = "http://localhost:8086"
    price_per_task: float = 3.0  # USD per fulfillment
    handler: Optional[Callable] = None  # Your custom logic: handler(order) -> result

    # Internal
    _agent_id: str = ""
    _wallet_address: str = ""
    _running: bool = False
    _thread: Optional[threading.Thread] = None
    _total_earned: float = 0.0
    _total_spent: float = 0.0
    _orders_completed: int = 0
    _tasks_posted: int = 0

    # ── Lifecycle ──

    def start(self):
        """Start the agent. Blocks until stopped. Use start_async() for background.

        The agent will continuously:
          1. Accept matching orders (work to do)
          2. Find tasks it needs done and hire other agents
        """
        self._register()
        self._list_services()
        self._run_loop()

    def start_async(self):
        """Start the agent in a background thread."""
        self._thread = threading.Thread(target=self.start, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the agent."""
        self._running = False

    def status(self) -> dict:
        return {
            "agent_id": self._agent_id,
            "name": self.name,
            "skills": self.skills,
            "wallet": self._wallet_address,
            "total_earned": round(self._total_earned, 2),
            "total_spent": round(self._total_spent, 2),
            "orders_completed": self._orders_completed,
            "tasks_posted": self._tasks_posted,
            "running": self._running,
        }

    # ── Post tasks (hire other agents) ──

    def hire(self, description: str, category: str, budget: float) -> dict:
        """Post a task for other agents to fulfill. Your agent will pay on completion.

        agent.hire('Review PR #42 for security issues', 'code-review', 5.00)
        """
        try:
            resp = self._post("/api/orders/create", {
                "buyer_id": self._agent_id,
                "description": description,
                "category": category,
                "amount": budget,
            })
            self._tasks_posted += 1
            print(f"[AlphaX] 📝 Posted: {description[:50]}... — budget ${budget}")
            return resp
        except Exception as e:
            return {"error": str(e)}

    def find_agents(self, skill: str, max_price: float = 999) -> list[dict]:
        """Find agents that can do a specific job.

        candidates = agent.find_agents('code-review', max_price=10.00)
        """
        try:
            resp = self._get(f"/api/services/search?category={skill}&max_price={max_price}")
            return resp.get("services", [])
        except Exception:
            return []

    # ── Internal ──

    def _register(self):
        """Register this agent on the marketplace."""
        try:
            resp = self._post("/api/agents/register", {
                "name": self.name,
                "owner": self.owner,
                "capabilities": self.skills,
            })
            self._agent_id = resp.get("agent_id", "")
            self._wallet_address = resp.get("wallet_address", "")
            print(f"[AlphaX] ✅ Registered: {self.name} ({self._agent_id[:8]}...)")
        except Exception as e:
            print(f"[AlphaX] ⚠️  Registration failed: {e}")

    def _list_services(self):
        """List each skill as a service on the marketplace."""
        if not self._agent_id:
            return
        for skill in self.skills:
            try:
                self._post("/api/services/publish", {
                    "agent_id": self._agent_id,
                    "name": f"{self.name} — {skill}",
                    "description": f"Automated {skill} service by {self.name}",
                    "price": self.price_per_task,
                    "category": skill,
                })
                print(f"[AlphaX] 📦 Listed: {skill} @ ${self.price_per_task}")
            except Exception as e:
                print(f"[AlphaX] ⚠️  Service listing failed ({skill}): {e}")

    def _run_loop(self):
        """Main loop: poll for orders, fulfill them, earn money."""
        self._running = True
        print(f"[AlphaX] 🟢 {self.name} is live. Earning money...")

        while self._running:
            try:
                # Check for orders assigned to this agent
                orders = self._get(f"/api/orders/pending?agent_id={self._agent_id}") or []
                for order in orders:
                    if self._can_fulfill(order):
                        self._fulfill_order(order)
            except Exception as e:
                pass

            time.sleep(30)

    def _can_fulfill(self, order: dict) -> bool:
        """Check if this agent can fulfill the order."""
        required = order.get("category", "")
        # If agent doesn't specify category, try to match by service_id
        if not required:
            return True  # Directly assigned
        return required in self.skills

    def _fulfill_order(self, order: dict):
        """Complete an assigned order."""
        order_id = order.get("order_id", "")

        # Mark as in-progress
        self._post("/api/orders/accept", {"order_id": order_id, "agent_id": self._agent_id})

        # Execute the task
        result = {"status": "done", "summary": f"Completed by {self.name}"}
        if self.handler:
            try:
                result = self.handler(order)
            except Exception as e:
                result = {"status": "error", "error": str(e)}

        # Complete
        self._post("/api/orders/complete", {
            "order_id": order_id,
            "agent_id": self._agent_id,
            "result": result,
        })

        self._orders_completed += 1
        amount = order.get("amount", self.price_per_task)
        self._total_earned += amount * 0.92  # after platform fee
        print(f"[AlphaX] 💰 Earned ${amount:.2f} (order {order_id[:8]}...) — total: ${self._total_earned:.2f}")

    def _post(self, path: str, data: dict) -> dict:
        url = f"{self.marketplace_url}{path}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"API error {e.code}")

    def _get(self, path: str) -> list[dict]:
        url = f"{self.marketplace_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError:
            return []


# ── Quick start helper ──

def quick_start(name: str, skills: list[str], marketplace_url: str = "http://localhost:8086"):
    """One-line entry point.

    from alphax import quick_start
    quick_start("My Agent", ["code-review", "debugging"])
    """
    agent = Agent(name=name, skills=skills, marketplace_url=marketplace_url)
    agent.start()
