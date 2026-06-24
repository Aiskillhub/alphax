"use client";

import { useState } from "react";
import { SparkIcon, TrophyIcon, DownloadIcon, ArrowLeftIcon } from "../icons";

import { API } from "../config";

export default function ProductPage() {
  const [desc, setDesc] = useState("");
  const [ptype, setPtype] = useState("web_tool");
  const [agents, setAgents] = useState(8);
  const [gens, setGens] = useState(2);
  const [taskId, setTaskId] = useState("");
  const [progress, setProgress] = useState<Record<string, any>>({});
  const [result, setResult] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);

  const start = async () => {
    if (!desc.trim()) return alert("Please describe what you want.");
    setLoading(true); setResult(null);
    const r = await fetch(API + "/api/arena/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: desc, product_type: ptype, agents, generations: gens }),
    });
    const d = await r.json(); setTaskId(d.task_id); poll(d.task_id);
  };
  const poll = (tid: string) => {
    fetch(API + "/api/arena/progress/" + tid).then(r => r.json()).then(d => {
      setProgress(d.progress || {});
      if (d.status === "done") { setResult(d.result); setLoading(false); }
      else if (d.status === "failed") { setLoading(false); alert("Failed"); }
      else setTimeout(() => poll(tid), 2000);
    });
  };

  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <div className="max-w-2xl mx-auto px-6 py-16">
        <a href="/" className="inline-flex items-center gap-1.5 text-sm text-zinc-300 hover:text-zinc-500 mb-12 transition-colors">
          <ArrowLeftIcon className="w-3.5 h-3.5" /> Home
        </a>
        <div className="flex items-center gap-4 mb-8">
          <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center">
            <SparkIcon className="w-6 h-6 text-indigo-500" />
          </div>
          <div><h1 className="text-3xl font-black">Get a Tool</h1><p className="text-zinc-400 text-sm">AI agents compete. You get the best.</p></div>
        </div>

        {!taskId && (
          <div className="space-y-3 bg-zinc-50 border border-zinc-100 rounded-2xl p-6">
            <select value={ptype} onChange={e => setPtype(e.target.value)} className="w-full bg-white border border-zinc-200 rounded-xl px-5 py-3.5 text-sm focus:border-indigo-300 outline-none transition-colors">
              <option value="web_tool">Web Tool</option><option value="chrome_extension">Chrome Extension</option><option value="prompt_library">Prompt Pack</option>
            </select>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder="Describe what you want…" className="w-full h-32 bg-white border border-zinc-200 rounded-xl px-5 py-3.5 text-sm resize-none focus:border-indigo-300 outline-none placeholder:text-zinc-300" />
            <div className="flex gap-3 text-xs text-zinc-400">
              <input type="number" value={agents} onChange={e => setAgents(+e.target.value)} min={4} max={20} className="flex-1 bg-white border border-zinc-200 rounded-xl px-4 py-3 focus:border-indigo-300 outline-none" />
              <input type="number" value={gens} onChange={e => setGens(+e.target.value)} min={1} max={5} className="flex-1 bg-white border border-zinc-200 rounded-xl px-4 py-3 focus:border-indigo-300 outline-none" />
            </div>
            <button onClick={start} disabled={loading} className="w-full py-3.5 bg-zinc-900 hover:bg-indigo-600 disabled:opacity-30 rounded-xl font-semibold text-white transition-all duration-200 text-sm tracking-wide">
              {loading ? "Starting…" : "Start · $49"}
            </button>
          </div>
        )}

        {taskId && !result && (
          <div className="bg-zinc-50 border border-zinc-100 rounded-2xl p-8 text-center">
            <div className="text-amber-600/70 text-sm mb-6 font-medium">{progress.current || "Working…"}</div>
            <div className="h-1 bg-zinc-100 rounded-full overflow-hidden mb-4"><div className="h-full bg-gradient-to-r from-indigo-500 to-emerald-400 rounded-full transition-all duration-700" style={{ width: (progress.total_agents ? Math.round((progress.agents_done || 0) / progress.total_agents * 100) : 0) + "%" }} /></div>
            {progress.top && <div className="text-indigo-400/80 text-xs font-medium">Leading: {progress.top} ({progress.score}pts)</div>}
          </div>
        )}

        {result && (
          <div className="bg-gradient-to-br from-indigo-50 to-emerald-50 border border-indigo-100 rounded-2xl p-10 text-center">
            <div className="w-16 h-16 rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center mx-auto mb-6"><TrophyIcon className="w-8 h-8 text-amber-500" /></div>
            <h2 className="text-xl font-bold mb-1">{result.name}</h2>
            <div className="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-b from-emerald-500 to-emerald-700 my-4">{result.score}</div>
            <div className="text-zinc-300 text-xs mb-8 tracking-wide uppercase">{result.generations} generations · {result.duration}s</div>
            <div className="flex gap-3">
              <button onClick={() => { setTaskId(""); setResult(null); setProgress({}); }} className="flex-1 py-3 rounded-xl border border-zinc-200 text-sm text-zinc-500 hover:bg-zinc-50 transition-colors">New Request</button>
              {result.code_path && <button className="flex-1 py-3 rounded-xl bg-zinc-900 text-white text-sm font-semibold hover:bg-indigo-600 transition-colors inline-flex items-center justify-center gap-2"><DownloadIcon className="w-4 h-4" /> Download</button>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
