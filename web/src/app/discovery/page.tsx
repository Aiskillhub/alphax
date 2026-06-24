"use client";

import { useState, useEffect } from "react";
import { AgentIcon, NetworkIcon, CheckIcon, ArrowLeftIcon } from "../icons";

import { API } from "../config";

export default function DiscoveryPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [stats, setStats] = useState({ total_agents: 0, mrr: 0 });
  const [name, setName] = useState("");
  const [skills, setSkills] = useState("");
  const [tier, setTier] = useState("free");
  const [msg, setMsg] = useState("");

  const refresh = () => {
    fetch(API + "/api/discovery/agents").then(r => r.json()).then(setAgents);
    fetch(API + "/api/discovery/stats").then(r => r.json()).then(d => setStats({ total_agents: d.total_agents, mrr: d.mrr }));
  };
  useEffect(() => { refresh(); const t = setInterval(refresh, 10000); return () => clearInterval(t); }, []);

  const register = async () => {
    if (!name) return;
    const r = await fetch(API + "/api/discovery/register", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: crypto.randomUUID().slice(0, 12), name, skills: skills.split(",").map(s => s.trim()).filter(Boolean), tier }),
    });
    const d = await r.json(); setMsg(`Registered as ${d.tier}`); setTimeout(refresh, 1000);
  };

  const tierBadge = (t: string) => {
    const m: Record<string, string> = {
      enterprise: "bg-indigo-50 border-indigo-200 text-indigo-600",
      pro: "bg-amber-50 border-amber-200 text-amber-600",
      free: "bg-zinc-50 border-zinc-200 text-zinc-400",
    };
    const labels: Record<string, string> = { enterprise: "Enterprise", pro: "Pro", free: "Free" };
    return <span className={`inline-flex px-2.5 py-0.5 rounded-md text-[11px] font-medium border ${m[t] || m.free}`}>{labels[t] || "Free"}</span>;
  };

  return (
    <div className="min-h-screen bg-white text-zinc-900">
      <div className="max-w-3xl mx-auto px-6 py-16">
        <a href="/" className="inline-flex items-center gap-1.5 text-sm text-zinc-300 hover:text-zinc-500 mb-12 transition-colors"><ArrowLeftIcon className="w-3.5 h-3.5" /> Home</a>

        <div className="flex items-center gap-4 mb-8">
          <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center"><NetworkIcon className="w-6 h-6 text-indigo-500" /></div>
          <div><h1 className="text-3xl font-black">Agent Discovery</h1><p className="text-zinc-400 text-sm">P2P network. Free to join. Pay for priority.</p></div>
        </div>

        <div className="flex gap-4 mb-8">
          <div className="flex-1 bg-zinc-50 border border-zinc-100 rounded-2xl p-5 text-center">
            <div className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-b from-emerald-500 to-emerald-700">{stats.total_agents}</div>
            <div className="text-[11px] text-zinc-300 uppercase tracking-widest mt-1">Agents</div>
          </div>
          <div className="flex-1 bg-zinc-50 border border-zinc-100 rounded-2xl p-5 text-center">
            <div className="text-3xl font-black text-transparent bg-clip-text bg-gradient-to-b from-emerald-500 to-emerald-700">${stats.mrr}</div>
            <div className="text-[11px] text-zinc-300 uppercase tracking-widest mt-1">MRR</div>
          </div>
        </div>

        <div className="bg-zinc-50 border border-zinc-100 rounded-2xl p-6 mb-6">
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2"><AgentIcon className="w-4 h-4 text-zinc-400" /> Register Agent</h3>
          <div className="flex gap-2.5 flex-wrap">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="Name" className="flex-1 min-w-[120px] bg-white border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:border-indigo-300 outline-none placeholder:text-zinc-300" />
            <input value={skills} onChange={e => setSkills(e.target.value)} placeholder="Skills" className="flex-1 min-w-[120px] bg-white border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:border-indigo-300 outline-none placeholder:text-zinc-300" />
            <select value={tier} onChange={e => setTier(e.target.value)} className="bg-white border border-zinc-200 rounded-xl px-4 py-2.5 text-sm focus:border-indigo-300 outline-none">
              <option value="free">Free</option><option value="pro">Pro $5/mo</option><option value="enterprise">Enterprise $49/mo</option>
            </select>
            <button onClick={register} className="px-5 py-2.5 bg-zinc-900 hover:bg-indigo-600 rounded-xl text-xs font-semibold text-white transition-colors inline-flex items-center gap-1.5"><CheckIcon className="w-3.5 h-3.5" /> Register</button>
          </div>
          {msg && <div className="text-emerald-600 text-xs mt-3 font-medium">{msg}</div>}
        </div>

        <div className="bg-zinc-50 border border-zinc-100 rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-zinc-100 text-zinc-300 text-[11px] uppercase tracking-wider">
              <th className="text-left px-5 py-3.5 font-medium">Name</th><th className="text-left px-5 py-3.5 font-medium">Skills</th><th className="text-left px-5 py-3.5 font-medium">Tier</th><th className="text-right px-5 py-3.5 font-medium">Rep</th>
            </tr></thead>
            <tbody>
              {agents.map(a => (
                <tr key={a.id} className="border-b border-zinc-50 hover:bg-white transition-colors">
                  <td className="px-5 py-3.5 font-medium">{a.name}</td><td className="px-5 py-3.5 text-zinc-400 text-xs">{a.skills.join(", ") || "—"}</td>
                  <td className="px-5 py-3.5">{tierBadge(a.tier)}</td><td className="px-5 py-3.5 text-right font-mono text-xs text-emerald-600">{(a.reputation * 5).toFixed(1)}</td>
                </tr>
              ))}
              {agents.length === 0 && <tr><td colSpan={4} className="text-center py-12 text-zinc-200 text-sm">No agents registered yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
