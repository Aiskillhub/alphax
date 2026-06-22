"""AlphaX Storefront — 产品销售入口

自建数字商品商店，0% 平台费。
支持产品展示、在线 Demo、下单、License Key 分发。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from config import config

stripe = None
if config.stripe_secret_key:
    try:
        import stripe as _stripe
        _stripe.api_key = config.stripe_secret_key
        stripe = _stripe
    except ImportError:
        pass

log = logging.getLogger("alphax.storefront")

STORE_DIR = config.data_dir / "store"
PRODUCTS_FILE = STORE_DIR / "products.json"
ORDERS_FILE = STORE_DIR / "orders.jsonl"
LICENSE_KEYS_FILE = STORE_DIR / "license_keys.jsonl"
ANALYTICS_FILE = STORE_DIR / "analytics.jsonl"

BUILDS_DIR = config.data_dir / "builds"


class LicenseGenerator:
    PREFIX = "AX"

    @classmethod
    def generate(cls, product_id: str, customer_email: str) -> str:
        seed = f"{product_id}:{customer_email}:{time.time()}:{secrets.token_hex(8)}"
        code = hashlib.sha256(seed.encode()).hexdigest()[:16].upper()
        return f"{cls.PREFIX}-{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"

    @classmethod
    def verify(cls, key: str, product_id: str) -> bool:
        if not key.startswith(cls.PREFIX):
            return False
        parts = key.replace(f"{cls.PREFIX}-", "").split("-")
        return len(parts) == 4 and all(len(p) == 4 for p in parts)


class StorefrontDB:
    def __init__(self):
        STORE_DIR.mkdir(parents=True, exist_ok=True)
        self.products = json.loads(PRODUCTS_FILE.read_text()) if PRODUCTS_FILE.exists() else {}

    def save(self):
        PRODUCTS_FILE.write_text(json.dumps(self.products, indent=2))

    def add_product(self, pid: str, info: dict):
        if pid not in self.products:
            self.products[pid] = {**info, "created_at": datetime.now(timezone.utc).isoformat(), "sales": 0, "revenue": 0.0}
        self.save()

    def record_order(self, product_id: str, email: str, amount: float, license_key: str) -> str:
        order_id = f"ORD-{secrets.token_hex(6).upper()}"
        order = {"order_id": order_id, "product_id": product_id, "email": email, "amount": amount, "license_key": license_key, "timestamp": datetime.now(timezone.utc).isoformat()}
        with open(ORDERS_FILE, "a") as f:
            f.write(json.dumps(order) + "\n")
        if product_id in self.products:
            self.products[product_id]["sales"] += 1
            self.products[product_id]["revenue"] += amount
            self.save()
        with open(LICENSE_KEYS_FILE, "a") as f:
            f.write(json.dumps({"key": license_key, "product_id": product_id, "email": email, "activated": False, "created_at": order["timestamp"]}) + "\n")
        return order_id

    def get_metrics(self) -> dict:
        return {
            "products": len(self.products),
            "sales": sum(p.get("sales", 0) for p in self.products.values()),
            "revenue": round(sum(p.get("revenue", 0) for p in self.products.values()), 2),
        }

    def get_product_analytics(self, product_id: str) -> dict:
        views = orders = 0
        if ANALYTICS_FILE.exists():
            with open(ANALYTICS_FILE) as f:
                for line in f:
                    try:
                        if json.loads(line).get("product_id") == product_id:
                            views += 1
                    except json.JSONDecodeError:
                        pass
        if ORDERS_FILE.exists():
            with open(ORDERS_FILE) as f:
                for line in f:
                    try:
                        if json.loads(line).get("product_id") == product_id:
                            orders += 1
                    except json.JSONDecodeError:
                        pass
        return {"views": views, "orders": orders}


# ── HTML ──

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alpha X Store — AI-Crafted Digital Products</title>
<style>
:root{
  --bg:#f8fafc; --card:#fff; --border:#e2e8f0; --text:#0f172a; --muted:#64748b;
  --accent:#6366f1; --accent-hover:#4f46e5; --green:#10b981; --amber:#f59e0b;
  --shadow-sm:0 1px 2px rgba(0,0,0,.05); --shadow:0 1px 3px rgba(0,0,0,.1),0 1px 2px rgba(0,0,0,.06);
  --shadow-lg:0 10px 25px rgba(0,0,0,.08); --radius:12px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;-webkit-font-smoothing:antialiased}

/* ── Nav ── */
.nav{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 24px}
.nav-inner{max-width:1200px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;height:56px}
.nav-logo{font-weight:800;font-size:18px;color:var(--text);text-decoration:none;letter-spacing:-.02em;display:flex;align-items:center;gap:8px}
.nav-logo .dot{width:8px;height:8px;border-radius:50%;background:var(--accent);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.nav-links{display:flex;gap:24px;align-items:center}
.nav-links a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500;transition:color .15s}
.nav-links a:hover{color:var(--text)}

/* ── Hero ── */
.hero{background:#0b0f19;color:#fff;padding:100px 24px 80px;text-align:center;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:
  radial-gradient(circle at 20% 50%,rgba(99,102,241,.15),transparent 40%),
  radial-gradient(circle at 80% 30%,rgba(139,92,246,.1),transparent 40%),
  radial-gradient(circle at 50% 80%,rgba(6,182,212,.06),transparent 30%)}
.hero-grid{position:absolute;inset:0;background-image:radial-gradient(rgba(99,102,241,.12) 1px,transparent 1px);background-size:32px 32px;animation:gridShift 12s linear infinite;mask-image:radial-gradient(ellipse at 50% 40%,black 30%,transparent 70%)}
@keyframes gridShift{0%{transform:translate(0,0)}25%{transform:translate(8px,-8px)}50%{transform:translate(0,-16px)}75%{transform:translate(-8px,-8px)}100%{transform:translate(0,0)}}
.hero-particles{position:absolute;inset:0;overflow:hidden}
.hero-particle{position:absolute;width:2px;height:2px;border-radius:50%;background:var(--accent);animation:floatUp linear infinite;opacity:0}
@keyframes floatUp{0%{transform:translateY(100%) scale(0);opacity:0}10%{opacity:.8}90%{opacity:.2}100%{transform:translateY(-100vh) scale(1);opacity:0}}
@keyframes heroGlow{0%,100%{transform:translate(0,0)}50%{transform:translate(2%,-2%)}}
@keyframes scanDown{0%,100%{top:0;opacity:0}30%{opacity:1}70%{opacity:1}100%{top:100%;opacity:0}}
.hero-content{position:relative;z-index:1;max-width:640px;margin:0 auto}
.hero-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 14px;border:1px solid rgba(255,255,255,.15);border-radius:20px;font-size:12px;color:#a5b4fc;margin-bottom:24px;letter-spacing:.02em;background:rgba(255,255,255,.04)}
.hero-badge .live-dot{width:6px;height:6px;border-radius:50%;background:#10b981;animation:pulse 2s infinite}
.hero h1{font-size:clamp(32px,5vw,52px);font-weight:800;letter-spacing:-.03em;margin-bottom:16px;line-height:1.12}
.hero h1 span{background:linear-gradient(135deg,#818cf8,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:17px;color:#94a3b8;max-width:480px;margin:0 auto 40px;line-height:1.6}
.hero-stats{display:flex;gap:48px;justify-content:center;flex-wrap:wrap}
.hero-stat{text-align:center}
.hero-stat .val{font-size:32px;font-weight:800;font-variant-numeric:tabular-nums}
.hero-stat .lbl{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:.12em;margin-top:4px}

/* ── Toolbar ── */
.toolbar{max-width:1200px;margin:0 auto;padding:24px 24px 0;display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.search-box{flex:1;min-width:240px;position:relative}
.search-box input{width:100%;padding:10px 14px 10px 40px;border:1px solid var(--border);border-radius:10px;font-size:14px;background:var(--card);color:var(--text);outline:none;transition:border-color .2s,box-shadow .2s}
.search-box input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(99,102,241,.1)}
.search-box .search-icon{position:absolute;left:14px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:14px}
.filter-pills{display:flex;gap:6px;flex-wrap:wrap}
.filter-pill{padding:6px 14px;border:1px solid var(--border);border-radius:20px;font-size:12px;font-weight:500;cursor:pointer;background:var(--card);color:var(--muted);transition:all .15s;white-space:nowrap;user-select:none}
.filter-pill:hover{border-color:var(--accent);color:var(--accent)}
.filter-pill.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.sort-select{padding:8px 12px;border:1px solid var(--border);border-radius:10px;font-size:13px;background:var(--card);color:var(--text);cursor:pointer;outline:none}

/* ── Grid ── */
.section{padding:32px 24px 80px}
.section-inner{max-width:1200px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px}
.result-count{color:var(--muted);font-size:13px;margin-bottom:16px}

/* ── Card ── */
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;transition:transform .25s,box-shadow .25s,border-color .25s;display:flex;flex-direction:column;cursor:pointer;text-decoration:none;color:inherit}
.card:hover{transform:translateY(-4px);box-shadow:0 12px 40px rgba(99,102,241,.15),0 0 0 1px rgba(99,102,241,.25);border-color:rgba(99,102,241,.3)}
.card-preview{height:160px;display:flex;align-items:center;justify-content:center;font-size:40px;position:relative;overflow:hidden}
.card-preview::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,transparent 50%,rgba(0,0,0,.5) 100%);z-index:1}
.card-preview .scan-line{position:absolute;left:0;right:0;height:1px;background:rgba(99,102,241,.2);animation:scanDown 3.5s ease-in-out infinite;z-index:3;pointer-events:none}
.card-preview .cat-tag{position:absolute;top:12px;right:12px;padding:4px 10px;border-radius:14px;font-size:10px;font-weight:600;background:rgba(0,0,0,.5);backdrop-filter:blur(4px);color:#fff;z-index:2;letter-spacing:.02em;text-transform:uppercase}
.card-preview .p-icon{position:relative;z-index:1;filter:drop-shadow(0 2px 8px rgba(0,0,0,.3))}
.card-body{padding:18px;flex:1;display:flex;flex-direction:column;gap:8px}
.card-body h3{font-size:15px;font-weight:600;letter-spacing:-.01em;line-height:1.3}
.card-body .desc{color:var(--muted);font-size:13px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-footer{display:flex;align-items:center;justify-content:space-between;padding:0 18px 18px}
.card-footer .price{font-size:20px;font-weight:700;letter-spacing:-.02em}
.card-footer .price s{color:var(--muted);font-size:13px;font-weight:400;margin-left:6px}
.card-footer .btn{padding:8px 18px;background:linear-gradient(135deg,var(--accent),#8b5cf6);color:#fff;border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;transition:all .2s;letter-spacing:.01em}
.card-footer .btn:hover{background:linear-gradient(135deg,var(--accent-hover),#7c3aed);box-shadow:0 4px 15px rgba(99,102,241,.35)}

/* ── Empty ── */
.empty{text-align:center;padding:80px 20px;color:var(--muted)}
.empty .icon{font-size:56px;margin-bottom:16px;opacity:.6}
.empty h3{font-size:18px;color:var(--text);margin-bottom:8px}
.empty code{background:#f1f5f9;padding:4px 10px;border-radius:6px;font-size:13px}

/* ── Footer ── */
footer{text-align:center;padding:48px 24px;color:var(--muted);font-size:13px;border-top:1px solid var(--border)}
footer a{color:var(--accent);text-decoration:none;font-weight:500}

@media(max-width:640px){
  .hero{padding:48px 20px 40px}
  .hero h1{font-size:28px}
  .hero-stats{gap:24px}
  .toolbar{flex-direction:column;align-items:stretch}
  .grid{grid-template-columns:1fr}
}
</style>
</head>
<body>

<nav class="nav">
  <div class="nav-inner">
    <a href="/" class="nav-logo"><span class="dot"></span>Alpha X Store</a>
    <div class="nav-links">
      <a href="/">Products</a>
      <a href="#footer">About</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="hero-grid"></div>
  <div class="hero-particles" id="particles"></div>
  <div class="hero-content">
    <div class="hero-badge"><span class="live-dot"></span>AI AUTONOMOUSLY BUILDING</div>
    <h1>Digital Products <span>Auto-Crafted</span> by AI</h1>
    <p>Every product is designed, built, and deployed by autonomous AI — evolving through real market feedback to create what developers actually need.</p>
    <div class="hero-stats">__HERO__</div>
  </div>
</header>

<div class="toolbar">
  <div class="search-box">
    <span class="search-icon">🔍</span>
    <input type="text" id="searchInput" placeholder="Search products..." oninput="filter()">
  </div>
  <div class="filter-pills" id="filterPills"></div>
  <select class="sort-select" id="sortSelect" onchange="filter()">
    <option value="default">Featured</option>
    <option value="price-asc">Price: Low to High</option>
    <option value="price-desc">Price: High to Low</option>
    <option value="name">Name: A-Z</option>
  </select>
</div>

<section class="section">
  <div class="section-inner">
    <div class="result-count" id="resultCount"></div>
    <div class="grid" id="productGrid"></div>
    <div class="empty" id="emptyState" style="display:none">
      <div class="icon">📦</div>
      <h3>No products match your filter</h3>
      <p>Try a different search term or category.</p>
    </div>
  </div>
</section>

<footer id="footer">
  <p><strong>Alpha X Store</strong> &mdash; Autonomous Digital Product Engine</p>
  <p style="margin-top:4px;">0% platform fees. Instant delivery. &middot; <a href="/">Browse All Products</a></p>
</footer>

<script>
var ALL=[],activeCat='all';
__DATA__
function render(prods){
  if(prods.length===0){document.getElementById('emptyState').style.display='block';document.getElementById('productGrid').innerHTML='';document.getElementById('resultCount').textContent='';return}
  document.getElementById('emptyState').style.display='none';
  document.getElementById('resultCount').textContent='Showing '+prods.length+' product'+(prods.length>1?'s':'');
  var h='';
  for(var i=0;i<prods.length;i++){
    var p=prods[i];
    h+='<a class="card" href="/product/'+p._id+'">'+
      '<div class="card-preview" style="background:hsl('+p._hue+',35%,18%)">'+
        '<div class="scan-line"></div>'+
        '<span class="p-icon">'+p._icon+'</span>'+
        '<span class="cat-tag">'+p._cat+'</span>'+
      '</div>'+
      '<div class="card-body"><h3>'+esc(p.name)+'</h3>'+
        '<p class="desc">'+(p.desc||'')+'</p>'+
      '</div>'+
      '<div class="card-footer">'+
        '<span class="price">$'+p.price.toFixed(2)+'</span>'+
        '<span class="btn">View Details</span>'+
      '</div>'+
    '</a>';
  }
  document.getElementById('productGrid').innerHTML=h;
}
function filter(){
  var q=(document.getElementById('searchInput').value||'').toLowerCase();
  var sort=document.getElementById('sortSelect').value;
  var filtered=ALL.filter(function(p){
    if(activeCat!=='all'&&p._cat!==activeCat)return false;
    if(q&&p.name.toLowerCase().indexOf(q)===-1&&(p.desc||'').toLowerCase().indexOf(q)===-1)return false;
    return true;
  });
  if(sort==='price-asc')filtered.sort(function(a,b){return a.price-b.price});
  if(sort==='price-desc')filtered.sort(function(a,b){return b.price-a.price});
  if(sort==='name')filtered.sort(function(a,b){return a.name.localeCompare(b.name)});
  render(filtered);
}
function setCat(cat,el){
  activeCat=cat;
  document.querySelectorAll('.filter-pill').forEach(function(p){p.classList.remove('active')});
  el.classList.add('active');
  filter();
}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function initParticles(){
  var c=document.getElementById('particles'),n=30;
  for(var i=0;i<n;i++){
    var d=document.createElement('div');d.className='hero-particle';
    d.style.left=Math.random()*100+'%';
    d.style.animationDuration=(8+Math.random()*12)+'s';
    d.style.animationDelay=Math.random()*10+'s';
    d.style.width=(1+Math.random()*2)+'px';
    d.style.height=d.style.width;
    if(Math.random()>.5)d.style.background='#818cf8';
    c.appendChild(d);
  }
}
initParticles();
filter();
</script>
</body>
</html>"""

PRODUCT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} — Alpha X Store</title>
<style>
:root{{--bg:#f8fafc;--card:#fff;--border:#e2e8f0;--text:#0f172a;--muted:#64748b;--accent:#6366f1;--accent-hover:#4f46e5;--green:#10b981;--radius:14px}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;-webkit-font-smoothing:antialiased}}

.nav{{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.85);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 24px}}
.nav-inner{{max-width:1200px;margin:0 auto;display:flex;align-items:center;height:56px}}
.nav a{{color:var(--accent);text-decoration:none;font-size:14px;font-weight:600}}

.page{{max-width:1100px;margin:0 auto;padding:40px 24px}}
.layout{{display:grid;grid-template-columns:1fr 360px;gap:48px;align-items:start}}
@media(max-width:768px){{.layout{{grid-template-columns:1fr}}}}

/* Left */
.preview-box{{border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;background:#fff;margin-bottom:28px}}
.preview-bar{{display:flex;align-items:center;gap:8px;padding:10px 16px;background:#f8fafc;border-bottom:1px solid var(--border)}}
.preview-bar .dot{{width:10px;height:10px;border-radius:50%}}
.preview-bar .dot.r{{background:#ef4444}}.preview-bar .dot.y{{background:#f59e0b}}.preview-bar .dot.g{{background:#10b981}}
.preview-bar span{{font-size:11px;color:var(--muted);margin-left:4px}}
.preview-box iframe{{width:100%;height:520px;border:none;background:#fff}}

.main-info h1{{font-size:26px;font-weight:700;letter-spacing:-.02em;margin-bottom:6px}}
.main-info .subtitle{{color:var(--muted);font-size:15px;margin-bottom:12px}}
.main-info .type-badge{{display:inline-block;padding:3px 10px;background:#eef2ff;color:var(--accent);border-radius:6px;font-size:11px;font-weight:600;margin-bottom:24px}}
.desc-section{{margin-bottom:24px}}
.desc-section h3{{font-size:14px;font-weight:600;margin-bottom:8px}}
.desc-section p{{color:var(--muted);font-size:14px;line-height:1.7}}
.desc-section ul{{list-style:none;margin-top:12px}}
.desc-section ul li{{padding:5px 0;font-size:14px;color:var(--muted)}}
.desc-section ul li::before{{content:'✓ ';color:var(--green);font-weight:700}}

/* Right sidebar */
.sidebar{{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:28px;position:sticky;top:80px}}
.sidebar .big-price{{font-size:38px;font-weight:800;letter-spacing:-.02em;margin-bottom:2px}}
.sidebar .fee-note{{color:var(--green);font-size:13px;margin-bottom:20px}}
.sidebar .meta-row{{display:flex;justify-content:space-between;padding:8px 0;font-size:13px;color:var(--muted);border-bottom:1px solid var(--border)}}
.sidebar input{{padding:10px 14px;border:1px solid var(--border);border-radius:10px;font-size:14px;width:100%;margin-top:16px;outline:none}}
.sidebar input:focus{{border-color:var(--accent)}}
.sidebar .buy-btn{{width:100%;padding:14px;background:var(--accent);color:#fff;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;margin-top:10px;transition:background .15s}}
.sidebar .buy-btn:hover{{background:var(--accent-hover)}}
.sidebar .buy-btn:disabled{{opacity:.6;cursor:not-allowed}}
.sidebar .secure{{text-align:center;font-size:11px;color:var(--muted);margin-top:10px}}
.success-box{{display:none;padding:14px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px;margin-top:14px}}
.success-box.show{{display:block}}
.success-box .key{{font-family:'SF Mono',Monaco,monospace;font-size:15px;font-weight:700;background:#fff;padding:6px 10px;border-radius:6px;word-break:break-all;margin:6px 0;border:1px solid var(--border)}}
.success-box .dl{{display:block;text-align:center;padding:10px;background:var(--green);color:#fff;border-radius:8px;text-decoration:none;font-weight:600;margin-top:6px}}
.files-row{{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}}
.files-row code{{background:#f1f5f9;padding:3px 8px;border-radius:4px;font-size:11px}}
</style>
</head>
<body>
<nav class="nav"><div class="nav-inner"><a href="/">&larr; Back to Store</a></div></nav>
<div class="page">
  <div class="layout">
    <div>
      {demo_html}
      <div class="main-info">
        <h1>{name}</h1>
        <p class="subtitle">{subtitle}</p>
        <span class="type-badge">{product_type}</span>
      </div>
      <div class="desc-section">
        <h3>About This Product</h3>
        <p>{description}</p>
        {bullets_html}
      </div>
      {files_html}
    </div>
    <div class="sidebar">
      <div class="big-price">${price}</div>
      <div class="fee-note">One-time purchase &middot; Lifetime access</div>
      <div class="meta-row"><span>Type</span><span>{product_type}</span></div>
      <div class="meta-row"><span>License</span><span>Single user</span></div>
      <div class="meta-row"><span>Updates</span><span>Free forever</span></div>
      <div class="meta-row"><span>Delivery</span><span>Instant download</span></div>
      <input type="email" id="email" placeholder="your@email.com">
      <button class="buy-btn" onclick="purchase()">Buy Now — ${price}</button>
      <p class="secure">License key delivered instantly</p>
      <div class="success-box" id="success">
        <strong>Purchase Complete</strong>
        <div class="key" id="licenseDisplay"></div>
        <a class="dl" id="dlLink" href="#">Download Now</a>
      </div>
    </div>
  </div>
</div>
<script>
var productId='{product_id}',price={price},hasStripe={has_stripe};
async function purchase(){{
  var email=document.getElementById('email').value;
  if(!email){{alert('Please enter your email');return}}
  var btn=document.querySelector('.buy-btn');btn.disabled=true;btn.textContent='Processing...';
  if(hasStripe){{
    try{{
      var r=await fetch('/api/create-checkout-session',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{product_id:productId,email:email}})}});
      var d=await r.json();
      if(d.url){{window.location.href=d.url}}
      else{{throw new Error(d.error||'Stripe failed')}}
    }}catch(e){{alert('Failed: '+e.message);btn.disabled=false;btn.textContent='Buy Now — $'+price.toFixed(2)}}
  }}else{{
    try{{
      var r=await fetch('/api/order',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{product_id:productId,email:email,amount:price}})}});
      var d=await r.json();
      if(d.license_key){{
        document.getElementById('licenseDisplay').textContent=d.license_key;
        document.getElementById('dlLink').href=d.download_url;
        document.getElementById('success').classList.add('show');
        btn.textContent='Purchased';
      }}
    }}catch(e){{alert('Failed: '+e.message);btn.disabled=false;btn.textContent='Buy Now — $'+price.toFixed(2)}}
  }}
}}
</script>
<img src="/api/analytics/pixel?product_id={product_id}" width="1" height="1" alt="" style="display:none">
</body>
</html>"""


class StorefrontAPI(BaseHTTPRequestHandler):
    db: StorefrontDB = None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._serve_index()
        elif path == "/api/products":
            self._json(200, self.db.products)
        elif path == "/api/metrics":
            self._json(200, self.db.get_metrics())
        elif path == "/api/analytics/pixel":
            self._serve_pixel()
        elif path.startswith("/product/"):
            self._serve_product(path.split("/product/")[-1])
        elif path.startswith("/demo/"):
            self._serve_demo(path.split("/demo/")[-1])
        elif path.startswith("/download/"):
            self._handle_download(path)
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = json.loads(self.rfile.read(content_length))
        else:
            body = {}
        if path == "/api/order":
            self._handle_order(body)
        elif path == "/api/create-checkout-session":
            self._handle_create_checkout_session(body)
        elif path == "/api/webhook":
            self._handle_webhook()
        else:
            self._json(404, {"error": "not found"})

    def _handle_create_checkout_session(self, body: dict):
        if not stripe:
            return self._json(503, {"error": "payment not configured"})
        pid = body.get("product_id", "")
        if pid not in self.db.products:
            return self._json(404, {"error": "product not found"})
        p = self.db.products[pid]
        price_cents = int(p.get("price", 0) * 100)
        if price_cents <= 0:
            return self._json(400, {"error": "invalid price"})
        success_url = body.get("success_url", f"http://localhost:8085/product/{pid}?session={{CHECKOUT_SESSION_ID}}")
        cancel_url = body.get("cancel_url", f"http://localhost:8085/product/{pid}")
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": p.get("name", pid),
                            "description": (p.get("description") or "")[:500],
                        },
                        "unit_amount": price_cents,
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "product_id": pid,
                    "customer_email": body.get("email", ""),
                },
            )
            self._json(200, {"url": session.url, "session_id": session.id})
        except Exception as e:
            log.error(f"Stripe session create failed: {e}")
            self._json(500, {"error": str(e)})

    def _handle_webhook(self):
        if not stripe or not config.stripe_webhook_secret:
            return self._json(503, {"error": "webhook not configured"})
        sig = self.headers.get("Stripe-Signature", "")
        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)
        try:
            event = stripe.Webhook.construct_event(
                payload, sig, config.stripe_webhook_secret
            )
        except Exception as e:
            log.error(f"Webhook signature verification failed: {e}")
            return self._json(400, {"error": "invalid signature"})

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            pid = session.get("metadata", {}).get("product_id", "")
            email = session.get("metadata", {}).get("customer_email", "")
            amount = session.get("amount_total", 0) / 100.0
            if pid and pid in self.db.products:
                key = LicenseGenerator.generate(pid, email)
                self.db.record_order(pid, email, amount, key)
                log.info(f"Stripe payment: {pid} ${amount:.2f} → {email}")
        self._json(200, {"received": True})

    def _handle_order(self, body: dict):
        pid = body.get("product_id", "")
        if pid not in self.db.products:
            return self._json(404, {"error": "product not found"})
        key = LicenseGenerator.generate(pid, body.get("email", ""))
        oid = self.db.record_order(pid, body.get("email", ""), body.get("amount", 0), key)
        self._json(200, {"order_id": oid, "license_key": key, "download_url": f"/download/{pid}?key={key}"})

    def _handle_download(self, path: str):
        pid = path.split("/download/")[-1].split("?")[0]
        key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
        if not LicenseGenerator.verify(key, pid):
            return self._json(403, {"error": "invalid license"})
        zip_path = BUILDS_DIR / f"{pid}.zip"
        if not zip_path.exists():
            for f in BUILDS_DIR.glob(f"*{pid}*.zip"):
                zip_path = f
                break
        if not zip_path.exists():
            return self._json(404, {"error": "file not found"})
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{pid}.zip"')
        self.send_header("Content-Length", str(zip_path.stat().st_size))
        self.end_headers()
        self.wfile.write(zip_path.read_bytes())

    def _serve_product(self, pid: str):
        p = self.db.products.get(pid)
        if not p:
            return self._html("<h2>Product not found</h2>")
        demo_html = ""
        if p.get("type") == "web_tool" or p.get("category") == "web_tool":
            demo_html = f"""<div class="preview-box">
              <div class="preview-bar"><div class="dot r"></div><div class="dot y"></div><div class="dot g"></div><span>Live Demo</span></div>
              <iframe src="/demo/{pid}" sandbox="allow-scripts allow-same-origin"></iframe>
            </div>"""
        elif p.get("build_dir"):
            demo_html = f"""<div class="preview-box">
              <div class="preview-bar"><div class="dot r"></div><div class="dot y"></div><div class="dot g"></div><span>Live Demo</span></div>
              <iframe src="/demo/{pid}" sandbox="allow-scripts allow-same-origin"></iframe>
            </div>"""

        bullets = "".join(f"<li>{b}</li>" for b in p.get("bullets", []))
        bullets_html = f'<ul>{bullets}</ul>' if bullets else ""
        files_html = ""
        if p.get("files"):
            files_html = '<div class="desc-section"><h3>What\'s Included</h3><div class="files-row">' + "".join(f'<code>{f}</code>' for f in p["files"]) + '</div></div>'

        html = PRODUCT_HTML.format(
            name=p.get("name", pid),
            subtitle=p.get("subtitle", "")[:120],
            product_type=(p.get("type") or "digital").replace("_", " ").title(),
            demo_html=demo_html,
            description=p.get("description", "") or "An autonomous AI-generated digital product.",
            bullets_html=bullets_html,
            files_html=files_html,
            price=f'{p.get("price", 0):.2f}',
            product_id=pid,
            has_stripe="true" if stripe else "false",
        )
        self._html(html)

    def _serve_demo(self, pid: str):
        """Serve the web tool index.html for iframe demo"""
        web_dir = BUILDS_DIR / f"webtool_{pid[:12]}"
        if not web_dir.exists():
            # Try to find by partial match
            for d in BUILDS_DIR.iterdir():
                if d.is_dir() and d.name.startswith("webtool_") and pid[:12] in d.name:
                    web_dir = d
                    break
        demo_file = web_dir / "index.html" if web_dir.exists() else None
        if demo_file and demo_file.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(demo_file.read_bytes())
        else:
            self._json(404, {"error": "demo not available"})

    def _serve_pixel(self):
        params = parse_qs(urlparse(self.path).query)
        pid = params.get("product_id", [""])[0]
        if pid:
            with open(ANALYTICS_FILE, "a") as f:
                f.write(json.dumps({"product_id": pid, "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")
        pixel = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        self.send_response(200)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(pixel)

    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    def _serve_index(self):
        products = self.db.products
        count = len(products)

        # Build JS data array and collect categories
        js_items = []
        categories = set()
        for pid, p in list(products.items()):
            ptype = (p.get("type") or p.get("category") or "digital")
            pprice = p.get("price", 0)
            if not isinstance(pprice, (int, float)):
                try: pprice = float(pprice)
                except: pprice = 0
            pname = p.get("name", pid)
            pdesc = (p.get("description") or p.get("subtitle") or "")[:140]
            hue = abs(hash(pid)) % 360
            nlower = pname.lower()
            icon = "📦"
            if "web_tool" in ptype or "json" in nlower or "formatter" in nlower: icon = "🔧"
            elif "saas" in ptype: icon = "🚀"
            elif "api" in ptype: icon = "⚡"
            elif "data" in ptype: icon = "📊"
            elif "ai" in ptype or "chat" in ptype: icon = "🤖"
            elif "productivity" in ptype: icon = "⚡"
            cat_short = ptype.replace("_", " ").title()[:20]
            categories.add(cat_short)
            js_items.append(
                f'{{_id:"{pid}",_cat:"{cat_short}",_hue:{hue},_icon:"{icon}",name:{json.dumps(pname)},'
                f'desc:{json.dumps(pdesc)},price:{pprice}}}'
            )

        # Build filter pills
        pills_html = '<span class="filter-pill active" onclick="setCat(\'all\',this)">All</span>'
        for cat in sorted(categories):
            pills_html += f'<span class="filter-pill" onclick="setCat(\'{cat}\',this)">{cat}</span>'

        # Build hero stats
        hero_html = (
            f'<div class="hero-stat"><div class="val">{count:,}</div><div class="lbl">Products</div></div>'
            f'<div class="hero-stat"><div class="val">0%</div><div class="lbl">Platform Fee</div></div>'
            f'<div class="hero-stat"><div class="val">Instant</div><div class="lbl">Delivery</div></div>'
        )

        html = INDEX_HTML
        html = html.replace('__HERO__', hero_html)
        html = html.replace('__DATA__', f'ALL=[{",".join(js_items)}];')
        html = html.replace('<div class="filter-pills" id="filterPills"></div>',
                            f'<div class="filter-pills" id="filterPills">{pills_html}</div>')
        self._html(html)

    def log_message(self, *args): pass


def run_store(port: int = 8085):
    db = StorefrontDB()
    StorefrontAPI.db = db
    # Bootstrap from builds
    if BUILDS_DIR.exists():
        for zipf in BUILDS_DIR.glob("*.zip"):
            pid = zipf.stem
            if pid not in db.products:
                meta = {}
                for d in BUILDS_DIR.iterdir():
                    if d.is_dir() and d.name.startswith(pid[:12]) or d.name.replace("notion_","").replace("vscode_","").replace("prompt_","").replace("webtool_","") == pid[:12]:
                        lf = d / "listing.json"
                        if lf.exists():
                            meta = json.loads(lf.read_text())
                        break
                db.add_product(pid, {
                    "name": meta.get("title", pid.replace("_", " ").title()),
                    "subtitle": meta.get("subtitle", "")[:120],
                    "description": meta.get("description", "AlphaX generated product.")[:300],
                    "bullets": meta.get("bullets", []),
                    "price": meta.get("price_point", 9.99),
                    "type": meta.get("product_type", "digital"),
                    "category": meta.get("category", ""),
                    "files": [f.name for f in d.iterdir() if f.is_file()] if (d := next((x for x in BUILDS_DIR.iterdir() if x.is_dir() and x.name.startswith(pid[:12])), None)) else [],
                })
    server = HTTPServer(("0.0.0.0", port), StorefrontAPI)
    print(f"\n  Alpha X Store → http://localhost:{port}")
    print(f"  {len(db.products)} products listed | 0% platform fee\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def add_to_store(pid: str, name: str, description: str, price: float, product_type: str = "digital", **kwargs):
    db = StorefrontDB()
    db.add_product(pid, {"name": name, "description": description, "price": price, "type": product_type, **kwargs})


if __name__ == "__main__":
    import sys
    run_store(int(sys.argv[1]) if len(sys.argv) > 1 else 8085)
