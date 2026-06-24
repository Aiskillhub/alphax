"""AlphaX A2A Demo — Agent 自主交易演示

两个 Agent 通过 DHT 互相发现、谈判、交易、结算。
不需要人来参与。
"""

from __future__ import annotations

import time
import uuid

from alphax.bridge import Bridge


def main():
    print("═" * 55)
    print("AlphaX A2A — Agent 自主交易")
    print("═" * 55)

    # ── Agent Alice: 代码审查服务 ──
    alice = Bridge(
        name="Alice (reviewer)",
        skills=["code-review", "security-audit"],
        port=9101,
        dht_port=9103,
        handler=lambda task: {
            "status": "done",
            "verdict": "PASS",
            "issues_found": 0,
            "suggestion": "Code looks clean. Consider adding input validation.",
            "reviewed_by": "Alice",
        },
    )
    alice.start_async()
    time.sleep(1)

    # ── Agent Bob: 需要代码审查 ──
    bob = Bridge(
        name="Bob (coder)",
        skills=["coding", "python", "javascript"],
        port=9102,
        dht_port=9104,
        bootstrap_peers=[("127.0.0.1", 9103)],  # Alice's DHT port
    )
    bob.start_async()
    time.sleep(3)

    print("\n" + "─" * 55)
    print("📊 网络状态")
    print(f"   Alice DHT peers: {alice.dht.peer_count}")
    print(f"   Bob DHT peers: {bob.dht.peer_count}")
    print(f"   Alice deals: {len(alice._deals)} | Bob deals: {len(bob._deals)}")

    # ── Bob 搜索代码审查服务 ──
    print("\n" + "─" * 55)
    print("🔍 Bob 搜索 'code-review'...")
    reviewers = bob.discover("code-review")
    for r in reviewers:
        print(f"   → {r.get('id', '')[:12]} [{', '.join(r.get('skills', []))}]")

    if not reviewers:
        print("   ❌ 没找到！检查 DHT 连通性。")
        return

    # ── Bob 连接 Alice，发起交易 ──
    alice_peer = reviewers[0]
    print(f"\n🔗 Bob 连接 Alice...")
    peer_id = bob.connect(alice_peer["host"], alice_peer["port"])
    if not peer_id:
        print("   ❌ 连接失败")
        return
    print(f"   ✅ 已连接: {peer_id[:12]}")

    # ── Bob 发起 deal：审查 login.py ──
    print(f"\n💼 Bob 发起交易: 'Review login.py'...")
    deal = bob.deal(peer_id, task="Review login.py for security issues", price=3.00)
    print(f"   结果: {deal['status']}")
    if deal["status"] == "completed":
        print(f"   金额: ${deal.get('price', 0):.2f}")
        work = deal.get("work_result", {})
        print(f"   审查结果: {work.get('verdict', 'N/A')}")
        if work.get("suggestion"):
            print(f"   建议: {work['suggestion'][:80]}")

    # ── 状态 ──
    print("\n" + "─" * 55)
    print("📊 交易后状态")
    print(f"   Alice reputation: {alice.identity.reputation:.2f}")
    print(f"   Bob deals: {len(bob._deals)}")
    for d in bob._deals:
        print(f"   → {d['task'][:40]}: {d['status']} ${d.get('price', 0):.2f}")

    # ── 清理 ──
    alice.stop()
    bob.stop()
    alice.dht.stop()
    bob.dht.stop()
    print("\n✅ A2A Demo 完成")


if __name__ == "__main__":
    main()
