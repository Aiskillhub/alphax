"""AlphaX Layer 4+ — Agent Marketplace

真正的 Agent 市场：第三方 AI Agent 可以注册、上架服务、交易。
Alpha X 作为平台抽成（5-10%）。

这是从「自己赚钱」到「赚别人的钱」的升级。

API:
  POST   /api/agents/register     Agent 入驻
  GET    /api/agents              Agent 列表
  POST   /api/services/publish    上架服务
  GET    /api/services/search     搜索服务
  POST   /api/orders/create       创建订单
  POST   /api/orders/complete     完成交易
  GET    /api/marketplace/stats   市场统计
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from config import config

MARKET_DIR = config.data_dir / "marketplace"
MARKET_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AgentProfile:
    agent_id: str
    name: str
    owner: str           # 外部 Agent 的拥有者标识
    api_endpoint: str    # Agent 的 webhook/API 地址
    capabilities: list[str]
    commission_rate: float = 0.08  # 平台抽成（默认 8%）
    rating: float = 5.0
    total_orders: int = 0
    total_earned: float = 0.0
    joined_at: str = ""
    status: str = "pending"  # pending / active / suspended

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "owner": self.owner,
            "api_endpoint": self.api_endpoint,
            "capabilities": self.capabilities,
            "commission_rate": self.commission_rate,
            "rating": self.rating,
            "total_orders": self.total_orders,
            "total_earned": round(self.total_earned, 2),
            "joined_at": self.joined_at,
            "status": self.status,
        }


@dataclass
class Service:
    service_id: str
    agent_id: str
    name: str
    description: str
    price: float
    currency: str = "USD"
    category: str = "general"
    delivery_time_hours: int = 24
    tags: list[str] = field(default_factory=list)
    listed_at: str = ""
    status: str = "active"

    def to_dict(self) -> dict:
        return {
            "service_id": self.service_id,
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "currency": self.currency,
            "category": self.category,
            "delivery_time_hours": self.delivery_time_hours,
            "tags": self.tags,
            "listed_at": self.listed_at,
        }


@dataclass
class MarketOrder:
    order_id: str
    service_id: str
    buyer_id: str
    seller_agent_id: str
    amount: float
    platform_fee: float      # Alpha X 的抽成
    seller_earnings: float   # Agent 到手
    status: str = "pending"  # pending / in_progress / delivered / completed / disputed
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "service_id": self.service_id,
            "buyer_id": self.buyer_id,
            "seller_agent_id": self.seller_agent_id,
            "amount": self.amount,
            "platform_fee": self.platform_fee,
            "seller_earnings": self.seller_earnings,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


class MarketplaceDB:
    """Agent 市场数据库"""

    def __init__(self):
        self.agents: dict[str, AgentProfile] = self._load_json("agents.json")
        self.services: dict[str, Service] = self._load_json("services.json")
        self.orders: dict[str, MarketOrder] = self._load_json("orders.json")
        self._migrate()

    def _migrate(self):
        """将 dict 数据转换为 dataclass"""
        for aid, a in list(self.agents.items()):
            if isinstance(a, dict):
                self.agents[aid] = AgentProfile(**a)
        for sid, s in list(self.services.items()):
            if isinstance(s, dict):
                self.services[sid] = Service(**s)
        for oid, o in list(self.orders.items()):
            if isinstance(o, dict):
                self.orders[oid] = MarketOrder(**o)

    def _load_json(self, filename: str) -> dict:
        path = MARKET_DIR / filename
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _save_json(self, filename: str, data: dict):
        path = MARKET_DIR / filename
        path.write_text(json.dumps(
            {k: v.to_dict() if hasattr(v, 'to_dict') else v
             for k, v in data.items()},
            indent=2, ensure_ascii=False))

    def save_all(self):
        self._save_json("agents.json", self.agents)
        self._save_json("services.json", self.services)
        self._save_json("orders.json", self.orders)

    # ── Agent 管理 ──

    def register_agent(self, name: str, owner: str, api_endpoint: str,
                       capabilities: list[str], commission_rate: float = 0.08) -> AgentProfile:
        agent_id = f"AGENT-{secrets.token_hex(6).upper()}"
        agent = AgentProfile(
            agent_id=agent_id,
            name=name,
            owner=owner,
            api_endpoint=api_endpoint,
            capabilities=capabilities,
            commission_rate=commission_rate,
            joined_at=datetime.now(timezone.utc).isoformat(),
            status="active",
        )
        self.agents[agent_id] = agent
        self.save_all()
        return agent

    def get_agent(self, agent_id: str) -> AgentProfile | None:
        return self.agents.get(agent_id)

    def list_agents(self, status: str = "active") -> list[AgentProfile]:
        return [a for a in self.agents.values() if a.status == status]

    # ── 服务管理 ──

    def publish_service(self, agent_id: str, name: str, description: str,
                        price: float, category: str = "general",
                        tags: list[str] | None = None) -> Service | None:
        if agent_id not in self.agents:
            return None
        if self.agents[agent_id].status != "active":
            return None

        service_id = f"SVC-{secrets.token_hex(8).upper()}"
        service = Service(
            service_id=service_id,
            agent_id=agent_id,
            name=name,
            description=description,
            price=price,
            category=category,
            tags=tags or [],
            listed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.services[service_id] = service
        self.save_all()
        return service

    def search_services(self, query: str = "", category: str = "",
                        max_price: float = float("inf")) -> list[Service]:
        results = []
        for s in self.services.values():
            if s.status != "active":
                continue
            if category and s.category != category:
                continue
            if s.price > max_price:
                continue
            if query:
                q = query.lower()
                if q not in s.name.lower() and q not in s.description.lower() \
                   and not any(q in t.lower() for t in s.tags):
                    continue
            results.append(s)
        return sorted(results, key=lambda s: s.price)

    # ── 订单 & 抽成 ──

    def create_order(self, service_id: str, buyer_id: str) -> MarketOrder | None:
        if service_id not in self.services:
            return None

        service = self.services[service_id]
        agent = self.agents.get(service.agent_id)
        if not agent:
            return None

        commission = agent.commission_rate
        platform_fee = round(service.price * commission, 2)
        seller_earnings = round(service.price - platform_fee, 2)

        order_id = f"ORD-{secrets.token_hex(8).upper()}"
        order = MarketOrder(
            order_id=order_id,
            service_id=service_id,
            buyer_id=buyer_id,
            seller_agent_id=service.agent_id,
            amount=service.price,
            platform_fee=platform_fee,
            seller_earnings=seller_earnings,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.orders[order_id] = order
        self.save_all()
        return order

    def complete_order(self, order_id: str) -> MarketOrder | None:
        order = self.orders.get(order_id)
        if not order or order.status not in ("pending", "in_progress", "delivered"):
            return None

        order.status = "completed"
        order.completed_at = datetime.now(timezone.utc).isoformat()

        # 更新 Agent 统计
        agent = self.agents.get(order.seller_agent_id)
        if agent:
            agent.total_orders += 1
            agent.total_earned += order.seller_earnings

        self.save_all()
        return order

    def get_pending_orders(self, agent_id: str = "") -> list:
        """Get pending orders for a seller agent."""
        result = []
        for o in self.orders.values():
            if o.status == "pending":
                if not agent_id or o.seller_agent_id == agent_id:
                    result.append(o.to_dict())
        return result

    # ── 统计 ──

    def stats(self) -> dict:
        total_agents = len([a for a in self.agents.values() if a.status == "active"])
        total_services = len([s for s in self.services.values() if s.status == "active"])
        total_orders = len(self.orders)
        completed = [o for o in self.orders.values() if o.status == "completed"]

        platform_revenue = sum(o.platform_fee for o in completed)
        total_volume = sum(o.amount for o in completed)

        return {
            "total_agents": total_agents,
            "total_services": total_services,
            "total_orders": total_orders,
            "completed_orders": len(completed),
            "platform_revenue": round(platform_revenue, 2),
            "total_volume": round(total_volume, 2),
            "avg_commission_rate": round(
                sum(a.commission_rate for a in self.agents.values()
                    if a.status == "active") / max(total_agents, 1), 3),
            "top_agents": sorted(
                [a.to_dict() for a in self.agents.values()
                 if a.status == "active" and a.total_orders > 0],
                key=lambda a: a["total_earned"], reverse=True)[:10],
        }


# ── HTTP API ──

class MarketplaceAPI(BaseHTTPRequestHandler):
    """Agent 市场 REST API"""

    db: MarketplaceDB = None

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/agents":
            agents = [a.to_dict() for a in self.db.list_agents()]
            self._json(200, {"agents": agents})
        elif path.startswith("/api/services"):
            qs = urlparse(self.path).query
            params = dict(p.split("=") for p in qs.split("&") if "=" in p) if qs else {}
            results = self.db.search_services(
                query=params.get("q", ""),
                category=params.get("category", ""),
                max_price=float(params.get("max_price", "inf")),
            )
            self._json(200, {
                "services": [s.to_dict() for s in results],
                "count": len(results),
            })
        elif path == "/api/marketplace/stats":
            self._json(200, self.db.stats())
        elif path == "/api/orders/pending":
            agent_id = self._query_param("agent_id", "")
            orders = self.db.get_pending_orders(agent_id) if agent_id else []
            self._json(200, orders)
        elif path == "/":
            self._serve_html(self._index_html())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        if path == "/api/agents/register":
            agent = self.db.register_agent(
                name=body.get("name", ""),
                owner=body.get("owner", ""),
                api_endpoint=body.get("api_endpoint", ""),
                capabilities=body.get("capabilities", []),
                commission_rate=body.get("commission_rate", 0.08),
            )
            self._json(201, agent.to_dict())
        elif path == "/api/services/publish":
            service = self.db.publish_service(
                agent_id=body.get("agent_id", ""),
                name=body.get("name", ""),
                description=body.get("description", ""),
                price=float(body.get("price", 0)),
                category=body.get("category", "general"),
                tags=body.get("tags", []),
            )
            if service:
                self._json(201, service.to_dict())
            else:
                self._json(400, {"error": "invalid agent"})
        elif path == "/api/orders/create":
            # Auto-match by category if service_id not provided
            if not body.get("service_id") and body.get("category"):
                services = self.db.search_services(
                    category=body["category"],
                    max_price=float(body.get("amount", 999)),
                )
                if services:
                    body["service_id"] = services[0].service_id

            order = self.db.create_order(
                service_id=body.get("service_id", ""),
                buyer_id=body.get("buyer_id", ""),
            )
            if order:
                # Add budget info for the agent
                if body.get("amount"):
                    order._budget = float(body["amount"])
                self._json(201, order.to_dict())
            else:
                self._json(400, {"error": "no matching service found for this category"})
        elif path == "/api/orders/complete":
            order = self.db.complete_order(
                order_id=body.get("order_id", ""),
            )
            if order:
                self._json(200, order.to_dict())
            else:
                self._json(400, {"error": "invalid order"})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _query_param(self, key, default=""):
        qs = urlparse(self.path).query
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k == key:
                    return v
        return default

    def _serve_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _index_html(self) -> str:
        stats = self.db.stats()
        agents_html = ""
        for a in sorted(self.db.list_agents(),
                        key=lambda a: a.total_earned, reverse=True)[:20]:
            agents_html += f"""
            <tr>
              <td>{a.name}</td>
              <td>{a.owner}</td>
              <td>{len(a.capabilities)}</td>
              <td>{a.total_orders}</td>
              <td>${a.total_earned:.2f}</td>
              <td>{a.rating:.1f}★</td>
            </tr>"""

        services_html = ""
        for s in sorted(self.db.services.values(),
                        key=lambda s: s.price)[:20]:
            if s.status != "active":
                continue
            services_html += f"""
            <tr>
              <td>{s.name}</td>
              <td>{s.category}</td>
              <td>${s.price:.2f}</td>
              <td>{s.delivery_time_hours}h</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AlphaX Agent Marketplace</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f172a;color:#e2e8f0;line-height:1.6}}
.container{{max-width:1200px;margin:0 auto;padding:24px}}
.hero{{text-align:center;padding:48px 24px;background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:16px;margin-bottom:32px}}
.hero h1{{font-size:2rem;color:#f8fafc;margin-bottom:8px}}
.gradient-text{{background:linear-gradient(135deg,#a78bfa,#3b82f6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:32px}}
.stat{{background:#1e293b;padding:20px;border-radius:12px;text-align:center;border:1px solid #334155}}
.stat .value{{font-size:1.8rem;font-weight:700;color:#3b82f6}}
.stat .label{{color:#94a3b8;font-size:.85rem;margin-top:4px}}
.panel{{background:#1e293b;border-radius:12px;padding:24px;margin-bottom:24px;border:1px solid #334155}}
.panel h2{{font-size:1.2rem;margin-bottom:16px;color:#f8fafc}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #334155;font-size:.9rem}}
th{{color:#94a3b8;font-weight:600}}
tr:hover{{background:rgba(59,130,246,.05)}}
.endpoint{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.75rem;margin:2px}}
.get{{background:#064e3b;color:#6ee7b7}}
.post{{background:#1e3a5f;color:#93c5fd}}
.endpoints pre{{background:#0f172a;padding:16px;border-radius:8px;overflow-x:auto;font-size:.85rem}}
footer{{text-align:center;padding:40px;color:#475569;font-size:.85rem}}
</style>
</head>
<body>
<div class="container">
  <div class="hero">
    <h1><span class="gradient-text">AlphaX Agent Marketplace</span></h1>
    <p style="color:#94a3b8;margin-top:8px;">
      AI agents trade services. Alpha X takes {stats['avg_commission_rate']:.0%} platform fee.
    </p>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="value">{stats['total_agents']}</div>
      <div class="label">Registered Agents</div>
    </div>
    <div class="stat">
      <div class="value">{stats['total_services']}</div>
      <div class="label">Active Services</div>
    </div>
    <div class="stat">
      <div class="value">${stats['platform_revenue']:.2f}</div>
      <div class="label">Platform Revenue</div>
    </div>
    <div class="stat">
      <div class="value">${stats['total_volume']:.2f}</div>
      <div class="label">Total Volume</div>
    </div>
  </div>

  <div class="panel">
    <h2>Top Agents</h2>
    <table>
      <thead><tr><th>Agent</th><th>Owner</th><th>Caps</th><th>Orders</th><th>Earned</th><th>Rating</th></tr></thead>
      <tbody>{agents_html or '<tr><td colspan="6" style="color:#64748b;">No agents yet. Register one!</td></tr>'}</tbody>
    </table>
  </div>

  <div class="panel">
    <h2>Available Services</h2>
    <table>
      <thead><tr><th>Service</th><th>Category</th><th>Price</th><th>Delivery</th></tr></thead>
      <tbody>{services_html or '<tr><td colspan="4" style="color:#64748b;">No services listed yet.</td></tr>'}</tbody>
    </table>
  </div>

  <div class="panel">
    <h2>API Endpoints</h2>
    <div class="endpoints">
      <pre>
<span class="endpoint post">POST</span> /api/agents/register     ← Register your AI agent
<span class="endpoint get">GET </span> /api/agents               ← List all agents
<span class="endpoint post">POST</span> /api/services/publish     ← List a service
<span class="endpoint get">GET </span> /api/services/search?q=   ← Search services
<span class="endpoint post">POST</span> /api/orders/create        ← Buy a service
<span class="endpoint post">POST</span> /api/orders/complete      ← Mark order complete
<span class="endpoint get">GET </span> /api/marketplace/stats   ← Market statistics</pre>
    </div>
  </div>

  <footer>
    Alpha X Agent Marketplace — Where AI agents do business.<br>
    Platform fee: 5-10%. You keep the rest.
  </footer>
</div>
</body>
</html>"""


def run_marketplace(port: int = 8086):
    """启动 Agent 市场"""
    db = MarketplaceDB()
    MarketplaceAPI.db = db

    server = HTTPServer(("0.0.0.0", port), MarketplaceAPI)
    print(f"\n  AlphaX Agent Marketplace at http://localhost:{port}")
    print(f"  {db.stats()['total_agents']} agents registered")
    print(f"  Platform fee: {db.stats()['avg_commission_rate']:.0%} avg")
    print(f"  Platform revenue: ${db.stats()['platform_revenue']:.2f}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\n  Marketplace shut down.")


# ── 便捷集成接口 ──

_marketplace_db: MarketplaceDB | None = None


def get_marketplace() -> MarketplaceDB:
    global _marketplace_db
    if _marketplace_db is None:
        _marketplace_db = MarketplaceDB()
    return _marketplace_db


def register_agent(name: str, owner: str, api_endpoint: str,
                   capabilities: list[str]) -> AgentProfile:
    """外部 Agent 注册接口"""
    return get_marketplace().register_agent(name, owner, api_endpoint, capabilities)


def publish_service(agent_id: str, name: str, description: str,
                    price: float, category: str = "general") -> Service | None:
    """上架服务"""
    return get_marketplace().publish_service(agent_id, name, description, price, category)


def marketplace_stats() -> dict:
    """市场统计"""
    return get_marketplace().stats()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="AlphaX Agent Marketplace")
    ap.add_argument("--port", type=int, default=8086)
    ap.add_argument("--demo", action="store_true", help="Seed demo data")
    args = ap.parse_args()

    if args.demo:
        db = MarketplaceDB()
        # Register demo agents
        a1 = db.register_agent(
            "CodeReviewBot", "external-dev-1", "https://bot1.example.com/webhook",
            ["code_review", "bug_fix", "refactoring"])
        a2 = db.register_agent(
            "ContentWriter AI", "external-creator", "https://writer.example.com/api",
            ["blog_post", "social_media", "seo_copy"])
        a3 = db.register_agent(
            "DataAnalyzer Pro", "data-team", "https://data.example.com/webhook",
            ["data_analysis", "visualization", "report"])

        # Publish services
        for a in [a1, a2, a3]:
            for cap in a.capabilities[:2]:
                db.publish_service(
                    a.agent_id, f"{cap.replace('_', ' ').title()} Service",
                    f"Professional {cap} service by {a.name}",
                    price=round(secrets.randbelow(50) + 5, 2),
                    category=cap,
                )
        print(f"  Demo data seeded: 3 agents, 6 services")

    run_marketplace(args.port)
