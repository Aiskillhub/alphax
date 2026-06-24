"""AlphaX API — FastAPI 后端

启动：python3 api.py --port 8000

REST API:
  POST /api/arena/run          竞技场：10 Agent 生成产品
  GET  /api/arena/progress/{id} 进度查询
  POST /api/discovery/register  Agent 注册
  GET  /api/discovery/agents    Agent 列表
  GET  /api/discovery/stats     统计
  GET  /api/health              健康检查
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn
import zipfile
import io

import sys
sys.path.insert(0, str(Path(__file__).parent))

from arena import Arena
from arena_models import ArenaProgress
from discovery_service import DiscoveryService


# ── App ──

app = FastAPI(title="AlphaX API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 全局状态 ──

discovery = DiscoveryService()
arena_tasks: dict[str, dict] = {}


# ── Models ──

class ArenaRunRequest(BaseModel):
    description: str
    product_type: str = "web_tool"
    agents: int = 8
    generations: int = 2
    api_key: str = ""


class DiscoveryRegisterRequest(BaseModel):
    agent_id: str
    name: str
    skills: list[str] = []
    host: str = "127.0.0.1"
    port: int = 0
    tier: str = "free"


# ═══════════════════════════════════════
# Arena — Agent 竞技场
# ═══════════════════════════════════════

@app.post("/api/arena/run")
def arena_run(req: ArenaRunRequest):
    """启动 Arena 竞技：10 Agent 竞争生成最优产品。"""
    if not req.description.strip():
        raise HTTPException(400, "description required")

    task_id = uuid.uuid4().hex[:8]
    arena_tasks[task_id] = {
        "progress": ArenaProgress().__dict__,
        "result": None,
        "status": "running",
    }

    def run():
        try:
            arena = Arena(api_key=req.api_key)
            result = arena.run(
                description=req.description,
                product_type=req.product_type,
                n_agents=req.agents,
                n_generations=req.generations,
                on_progress=lambda p: arena_tasks[task_id].update(
                    progress=p.__dict__),
            )
            arena_tasks[task_id].update(
                status="done",
                result={
                    "name": result.winner_name,
                    "score": result.winner_score,
                    "code_path": result.winner_code_path,
                    "generations": result.total_generations,
                    "duration": result.total_duration_seconds,
                },
            )
        except Exception as e:
            arena_tasks[task_id].update(status="failed", result={"error": str(e)})

    threading.Thread(target=run, daemon=True).start()
    return {"task_id": task_id, "status": "started"}


@app.get("/api/arena/progress/{task_id}")
def arena_progress(task_id: str):
    """查询 Arena 任务进度。"""
    task = arena_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task


# ═══════════════════════════════════════
# Discovery — Agent 发现服务
# ═══════════════════════════════════════

@app.post("/api/discovery/register")
def discovery_register(req: DiscoveryRegisterRequest):
    """注册 Agent 到发现网络。"""
    listing = discovery.register(
        agent_id=req.agent_id or uuid.uuid4().hex[:12],
        name=req.name,
        skills=req.skills,
        host=req.host,
        port=req.port,
        tier=req.tier,
    )
    return {"status": "registered", "tier": listing.tier, "agent_id": listing.agent_id}


@app.get("/api/discovery/agents")
def discovery_agents(skill: str = ""):
    """查询已注册 Agent 列表（付费优先）。"""
    return discovery.discover(skill=skill, limit=50)


@app.get("/api/discovery/stats")
def discovery_stats():
    """发现网络统计。"""
    return discovery.stats()


# ── Health ──

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "AlphaX API",
        "discovery_agents": discovery.stats()["total_agents"],
        "arena_tasks": len(arena_tasks),
    }


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    print(f"🚀 AlphaX API → http://localhost:{args.port}")
    print(f"   Docs → http://localhost:{args.port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
