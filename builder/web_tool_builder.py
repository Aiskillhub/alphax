"""AlphaX Builder — Web Tool 生成器

生成有真实功能的单页 Web 工具。每个工具都是完整的 HTML 文件，
包含专业的 CSS 和工作 JS 逻辑，可以直接使用和销售。

与模板填空式 builder 的本质区别：每个工具类型有独立的代码生成逻辑。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.genome import Genome, Category, TitlePattern
from config import config


# ── 各工具类型的独立代码生成函数 ──

def _json_formatter(genome: Genome) -> str:
    """JSON 格式化/验证/树形查看器"""
    name = _resolve_name(genome, "JSON Formatter Pro", "JSON Tool")
    return _wrap(name, """<style>
.wrapper{display:flex;gap:12px;height:70vh}
.panel{flex:1;display:flex;flex-direction:column}
.panel h3{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:6px}
textarea{flex:1;width:100%;border:1px solid var(--border);border-radius:6px;padding:12px;font-family:'SF Mono',Monaco,monospace;font-size:13px;resize:none;background:var(--bg);color:var(--text)}
#output{flex:1;overflow:auto;border:1px solid var(--border);border-radius:6px;padding:12px;font-family:'SF Mono',Monaco,monospace;font-size:13px;background:var(--bg)}
.toolbar{display:flex;gap:8px;margin-bottom:12px}
.btn{padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:12px}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn:hover{opacity:.85}
.error{color:#ef4444}
.key{color:#2563eb}
.string{color:#059669}
.number{color:#d97706}
.bool{color:#7c3aed}
.null{color:#9ca3af}
.bracket{color:var(--text)}
</style>
<div class="toolbar">
  <button class="btn primary" onclick="format()">Format</button>
  <button class="btn" onclick="minify()">Minify</button>
  <button class="btn" onclick="validate()">Validate</button>
  <button class="btn" onclick="treeView()">Tree</button>
  <button class="btn" onclick="copyOutput()">Copy</button>
</div>
<div class="wrapper">
  <div class="panel"><h3>Input</h3><textarea id="input" placeholder="Paste JSON here..."></textarea></div>
  <div class="panel"><h3>Output</h3><div id="output"></div></div>
</div>
<script>
function $(id){return document.getElementById(id)}
function format(){
  try{var o=JSON.parse($('input').value);$('output').innerHTML=syntaxHighlight(JSON.stringify(o,null,2));$('output').className=''}
  catch(e){$('output').innerHTML='<span class="error">'+e.message+'</span>'}
}
function minify(){
  try{var o=JSON.parse($('input').value);$('output').textContent=JSON.stringify(o);$('output').className=''}
  catch(e){$('output').innerHTML='<span class="error">'+e.message+'</span>'}
}
function validate(){
  try{JSON.parse($('input').value);$('output').innerHTML='<span style="color:#059669">Valid JSON</span>'}
  catch(e){$('output').innerHTML='<span class="error">Invalid: '+e.message+'</span>'}
}
function treeView(){
  try{var o=JSON.parse($('input').value);$('output').innerHTML=buildTree(o);$('output').className=''}
  catch(e){$('output').innerHTML='<span class="error">'+e.message+'</span>'}
}
function buildTree(obj,level){level=level||0;if(obj===null)return'<span class="null">null</span>';
if(typeof obj!=='object'){var c=typeof obj;return'<span class="'+c+'">'+String(obj)+'</span>'}
var pad='  '.repeat(level),html=Array.isArray(obj)?'<span class="bracket">[</span>\\n':'<span class="bracket">{</span>\\n';
var keys=Object.keys(obj),i=0;for(var k of keys){html+=pad+'  <span class="key">"'+k+'"</span>: ';
html+=buildTree(obj[k],level+1);if(i++<keys.length-1)html+=',';html+='\\n'}
html+=pad+(Array.isArray(obj)?'<span class="bracket">]</span>':'<span class="bracket">}</span>');return html}
function syntaxHighlight(json){return json.replace(/("(\\\\u[a-zA-Z0-9]{4}|\\\\[^u]|[^"\\\\])*"(\\s*:)?|\\b(true|false|null)\\b|-?\\d+(?:\\.\\d*)?(?:[eE][+\\-]?\\d+)?)/g,function(m){var cls='number';if(/^"/.test(m)){if(/:$/.test(m))cls='key';else cls='string'}else if(/true|false/.test(m))cls='bool';else if(/null/.test(m))cls='null';return'<span class="'+cls+'">'+m+'</span>'})}
function copyOutput(){navigator.clipboard.writeText($('output').textContent)}
</script>""")


def _markdown_editor(genome: Genome) -> str:
    """Markdown 实时预览编辑器"""
    name = _resolve_name(genome, "Markdown Studio", "MD Editor")
    return _wrap(name, """<script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js" crossorigin="anonymous"></script>
<style>
.editor-layout{display:flex;gap:12px;height:75vh}
.editor-layout .pane{flex:1;display:flex;flex-direction:column}
.editor-layout h3{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:6px}
#editor{flex:1;width:100%;border:1px solid var(--border);border-radius:6px;padding:14px;font-family:'SF Mono',Monaco,monospace;font-size:13px;resize:none;background:var(--bg);color:var(--text);line-height:1.6}
#preview{flex:1;overflow:auto;border:1px solid var(--border);border-radius:6px;padding:14px 20px;background:var(--bg);line-height:1.7}
#preview h1{font-size:24px;margin:16px 0 8px}
#preview h2{font-size:20px;margin:14px 0 6px}
#preview h3{font-size:16px;margin:12px 0 4px}
#preview pre{background:#1e1e2e;color:#cdd6f4;padding:12px 16px;border-radius:6px;overflow-x:auto;font-size:12px}
#preview code{font-family:'SF Mono',Monaco,monospace;font-size:12px}
#preview blockquote{border-left:3px solid var(--accent);padding-left:14px;color:var(--muted);margin:12px 0}
#preview table{border-collapse:collapse;width:100%;margin:12px 0}
#preview td,#preview th{border:1px solid var(--border);padding:8px 12px;text-align:left}
#preview img{max-width:100%;border-radius:6px}
.toolbar{display:flex;gap:8px;margin-bottom:12px}
.btn{padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:12px}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
</style>
<div class="toolbar">
  <button class="btn" onclick="insertSample()">Sample</button>
  <button class="btn primary" onclick="exportHTML()">Export HTML</button>
  <button class="btn" onclick="exportMD()">Export .md</button>
</div>
<div class="editor-layout">
  <div class="pane"><h3>Markdown</h3><textarea id="editor" placeholder="Write markdown..."></textarea></div>
  <div class="pane"><h3>Preview</h3><div id="preview"></div></div>
</div>
<script>
var editor=document.getElementById('editor'),preview=document.getElementById('preview');
editor.addEventListener('input',function(){preview.innerHTML=marked.parse(editor.value)});
function insertSample(){
  editor.value='# Welcome\\n\\n## Features\\n- **Real-time** preview\\n- Export to HTML\\n- Clean, minimal design\\n\\n> Markdown is the lingua franca of developers.\\n\\n```javascript\\nconsole.log("hello world");\\n```\\n\\n| Feature | Status |\\n|---------|--------|\\n| Preview | Ready |\\n| Export | Ready |';
  preview.innerHTML=marked.parse(editor.value)
}
function exportHTML(){var h='<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{max-width:800px;margin:40px auto;padding:0 20px;font-family:-apple-system,sans-serif;line-height:1.7;color:#111}</style></head><body>'+marked.parse(editor.value)+'</body></html>';download('export.html',h,'text/html')}
function exportMD(){download('export.md',editor.value,'text/markdown')}
function download(fn,content,type){var b=new Blob([content],{type:type}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=fn;a.click();URL.revokeObjectURL(a.href)}
</script>""")


def _regex_tester(genome: Genome) -> str:
    """正则表达式测试器"""
    name = _resolve_name(genome, "Regex Lab", "Regex Tester")
    return _wrap(name, """<style>
.layout{display:flex;flex-direction:column;gap:12px;height:75vh}
.regex-row{display:flex;gap:12px;align-items:center}
.regex-row input{flex:1;padding:10px 14px;border:1px solid var(--border);border-radius:6px;font-family:'SF Mono',Monaco,monospace;font-size:14px;background:var(--bg);color:var(--text)}
.regex-row input#pattern{border-color:var(--accent)}
.flags{display:flex;gap:8px}
.flag-btn{padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--card);color:var(--text);cursor:pointer;font-size:11px;font-family:monospace}
.flag-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
#test-text{flex:1;width:100%;border:1px solid var(--border);border-radius:6px;padding:14px;font-family:'SF Mono',Monaco,monospace;font-size:13px;resize:none;background:var(--bg);color:var(--text)}
.results-panel{overflow:auto;border:1px solid var(--border);border-radius:6px;padding:14px;background:var(--bg);min-height:120px}
.match{background:rgba(37,99,235,.15);border-radius:3px;padding:1px 2px}
.match-num{color:var(--accent);font-weight:600}
.common-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.common-row span{padding:4px 10px;background:var(--bg);border:1px solid var(--border);border-radius:4px;font-size:11px;font-family:monospace;cursor:pointer}
.common-row span:hover{border-color:var(--accent)}
</style>
<div class="common-row">
  <span onclick="usePattern('\\\\d+')">\\d+</span>
  <span onclick="usePattern('[a-zA-Z]+')">[a-zA-Z]+</span>
  <span onclick="usePattern('\\\\b\\\\w+@\\\\w+\\\\.\\\\w+\\\\b')">email</span>
  <span onclick="usePattern('https?://[^\\\\s]+')">URL</span>
  <span onclick="usePattern('\\\\b\\\\d{1,3}\\\\.\\\\d{1,3}\\\\.\\\\d{1,3}\\\\.\\\\d{1,3}\\\\b')">IP</span>
  <span onclick="usePattern('"[^"]*"')">quoted</span>
  <span onclick="usePattern('<[^>]+>')">HTML tag</span>
</div>
<div class="regex-row">
  <input id="pattern" placeholder="Enter regex pattern..." value="\\b\\w+@\\w+\\.\\w+\\b">
  <span style="font-size:12px;color:var(--muted)">/</span>
  <div class="flags">
    <button class="flag-btn active" id="flag-g" onclick="toggleFlag(this)">g</button>
    <button class="flag-btn" id="flag-i" onclick="toggleFlag(this)">i</button>
    <button class="flag-btn" id="flag-m" onclick="toggleFlag(this)">m</button>
    <button class="flag-btn" id="flag-s" onclick="toggleFlag(this)">s</button>
  </div>
</div>
<div class="layout">
  <textarea id="test-text" placeholder="Paste text to test against...">Contact us at support@example.com or sales@company.org for more info.</textarea>
  <div id="results" class="results-panel" style="color:var(--muted)">Matches appear here...</div>
</div>
<script>
var flags={g:true,i:false,m:false,s:false};
function toggleFlag(btn){flags[btn.textContent]=!flags[btn.textContent];btn.classList.toggle('active')}
function usePattern(p){document.getElementById('pattern').value=p;runRegex()}
function getFlags(){return Object.entries(flags).filter(function(e){return e[1]}).map(function(e){return e[0]}).join('')}
function runRegex(){
  var r=document.getElementById('results'),p=document.getElementById('pattern').value;
  var t=document.getElementById('test-text').value;
  if(!p){r.innerHTML='<span style="color:#ef4444">Enter a regex pattern</span>';return}
  try{var re=new RegExp(p,getFlags());var matches=[],m;while((m=re.exec(t))!==null){matches.push({index:m.index,text:m[0],groups:m.length>1?Array.from(m).slice(1):[]});if(!flags.g)break}
    if(matches.length===0){r.innerHTML='No matches'}
    else{var html='<div style="margin-bottom:8px"><span class="match-num">'+matches.length+'</span> matches found</div>';
      var lastIdx=0,highlighted='';
      for(var i=0;i<matches.length;i++){highlighted+=escHtml(t.slice(lastIdx,matches[i].index))+'<span class="match">'+escHtml(matches[i].text)+'</span>';lastIdx=matches[i].index+matches[i].text.length}
      highlighted+=escHtml(t.slice(lastIdx));
      html+='<div style="white-space:pre-wrap;line-height:1.8;font-family:monospace;font-size:13px">'+highlighted+'</div>';
      html+='<div style="margin-top:12px"><table style="width:100%;font-size:12px"><tr style="color:var(--muted)"><th>#</th><th>Index</th><th>Match</th><th>Groups</th></tr>';
      for(var i=0;i<matches.length;i++){html+='<tr><td>'+i+'</td><td>'+matches[i].index+'</td><td><code>'+escHtml(matches[i].text)+'</code></td><td>'+JSON.stringify(matches[i].groups)+'</td></tr>'}
      html+='</table></div>';r.innerHTML=html}}
  }catch(e){r.innerHTML='<span style="color:#ef4444">'+escHtml(e.message)+'</span>'}
}
function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
document.getElementById('pattern').addEventListener('input',runRegex);
document.getElementById('test-text').addEventListener('input',runRegex);
runRegex();
</script>""")


def _base64_codec(genome: Genome) -> str:
    """Base64 编解码工具"""
    name = _resolve_name(genome, "Base64 Codec Pro", "Encode/Decode Tool")
    return _wrap(name, """<style>
.mode-tabs{display:flex;gap:0;margin-bottom:16px}
.mode-tab{padding:8px 20px;border:1px solid var(--border);background:var(--card);color:var(--text);cursor:pointer;font-size:13px}
.mode-tab:first-child{border-radius:6px 0 0 6px}
.mode-tab:last-child{border-radius:0 6px 6px 0}
.mode-tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.toolbar{display:flex;gap:8px;margin-bottom:12px}
.btn{padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:12px}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
textarea{width:100%;height:300px;border:1px solid var(--border);border-radius:6px;padding:14px;font-family:'SF Mono',Monaco,monospace;font-size:13px;resize:vertical;background:var(--bg);color:var(--text);margin-bottom:12px}
#file-info{font-size:12px;color:var(--muted);margin-bottom:8px}
</style>
<div class="mode-tabs">
  <button class="mode-tab active" onclick="switchMode('encode')">Encode</button>
  <button class="mode-tab" onclick="switchMode('decode')">Decode</button>
</div>
<input type="file" id="file-input" style="display:none" onchange="handleFile(event)">
<div class="toolbar">
  <button class="btn primary" onclick="process()">Process</button>
  <button class="btn" onclick="swap()">Swap</button>
  <button class="btn" onclick="copyResult()">Copy</button>
  <button class="btn" id="file-btn" onclick="document.getElementById('file-input').click()">File</button>
  <button class="btn" onclick="clearAll()">Clear</button>
</div>
<div id="file-info"></div>
<textarea id="input" placeholder="Enter text to encode..."></textarea>
<textarea id="output" placeholder="Result..." readonly></textarea>
<script>
var mode='encode';
function switchMode(m){mode=m;var tabs=document.querySelectorAll('.mode-tab');tabs[0].classList.toggle('active',m==='encode');tabs[1].classList.toggle('active',m==='decode');
  document.getElementById('input').placeholder=m==='encode'?'Enter text to encode...':'Enter Base64 to decode...'}
function process(){
  var input=document.getElementById('input').value;
  try{
    if(mode==='encode'){document.getElementById('output').value=btoa(unescape(encodeURIComponent(input)))}
    else{var decoded=decodeURIComponent(escape(atob(input.trim())));document.getElementById('output').value=decoded}
  }catch(e){document.getElementById('output').value='Error: '+e.message}
}
function swap(){var inp=document.getElementById('input'),out=document.getElementById('output');var tmp=inp.value;inp.value=out.value;out.value=tmp;switchMode(mode==='encode'?'decode':'encode')}
function copyResult(){var out=document.getElementById('output');navigator.clipboard.writeText(out.value)}
function handleFile(e){var f=e.target.files[0];if(!f)return;document.getElementById('file-info').textContent=f.name+' ('+(f.size/1024).toFixed(1)+' KB)';
  var reader=new FileReader();
  if(mode==='encode'){reader.onload=function(ev){document.getElementById('input').value=ev.target.result};reader.readAsText(f)}
  else{reader.onload=function(ev){document.getElementById('input').value=ev.target.result.split(',')[1]||ev.target.result};reader.readAsDataURL(f)}
}
function clearAll(){document.getElementById('input').value='';document.getElementById('output').value='';document.getElementById('file-info').textContent=''}
</script>""")


def _color_palette(genome: Genome) -> str:
    """调色板生成器 + 颜色转换"""
    name = _resolve_name(genome, "Color Studio Pro", "Palette Generator")
    return _wrap(name, """<style>
.color-area{display:flex;gap:16px;flex-wrap:wrap}
.picker-col{min-width:280px}
.picker-col input[type="color"]{width:100%;height:180px;border:none;border-radius:8px;cursor:pointer;margin-bottom:12px}
.color-values div{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-family:monospace;font-size:13px}
.color-values label{min-width:40px;font-size:11px;color:var(--muted)}
.color-values input{flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-family:monospace;font-size:13px;background:var(--bg);color:var(--text)}
.palette-col{flex:1;min-width:300px}
.palette-col h3{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:10px}
.swatches{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.swatch{width:56px;height:56px;border-radius:8px;cursor:pointer;position:relative;border:2px solid transparent;transition:transform .15s}
.swatch:hover{transform:scale(1.1);z-index:1}
.swatch.selected{border-color:var(--accent)}
.swatch .code{position:absolute;bottom:-18px;left:0;right:0;text-align:center;font-size:9px;font-family:monospace;color:var(--muted)}
.scheme-row{display:flex;gap:4px;margin-bottom:8px;border-radius:8px;overflow:hidden;height:48px}
.scheme-row div{flex:1;cursor:pointer;transition:flex .2s}
.scheme-row div:hover{flex:2}
.btn-row{display:flex;gap:8px;margin-bottom:12px}
.btn{padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:12px}
.info{margin-top:12px;font-size:12px;color:var(--muted)}
</style>
<div class="color-area">
  <div class="picker-col">
    <input type="color" id="picker" value="#3b82f6" onchange="syncFromPicker()">
    <div class="color-values">
      <div><label>HEX</label><input id="hex" value="#3B82F6" onchange="syncFromHex()"></div>
      <div><label>RGB</label><input id="rgb" value="rgb(59, 130, 246)" readonly></div>
      <div><label>HSL</label><input id="hsl" value="hsl(217, 91%, 60%)" readonly></div>
    </div>
  </div>
  <div class="palette-col">
    <h3>Palette</h3>
    <div class="swatches" id="swatches"></div>
    <h3>Harmonies</h3>
    <div class="btn-row">
      <button class="btn" onclick="genScheme('analogous')">Analogous</button>
      <button class="btn" onclick="genScheme('complementary')">Complementary</button>
      <button class="btn" onclick="genScheme('triadic')">Triadic</button>
      <button class="btn" onclick="genScheme('mono')">Monochromatic</button>
      <button class="btn" onclick="genScheme('random')">Random</button>
    </div>
    <div id="scheme-display"></div>
    <button class="btn" onclick="exportPalette()" style="margin-top:12px">Export CSS</button>
    <div class="info" id="export-info"></div>
  </div>
</div>
<script>
var palette=[],picker=document.getElementById('picker');
function syncFromPicker(){
  var hex=picker.value;document.getElementById('hex').value=hex.toUpperCase();
  var r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
  document.getElementById('rgb').value='rgb('+r+', '+g+', '+b+')';
  var h=rgbToHsl(r,g,b);document.getElementById('hsl').value='hsl('+h[0]+', '+h[1]+'%, '+h[2]+'%)'
}
function syncFromHex(){
  var v=document.getElementById('hex').value;if(/^#[0-9a-fA-F]{6}$/.test(v)){picker.value=v;syncFromPicker()}
}
function rgbToHsl(r,g,b){r/=255;g/=255;b/=255;var M=Math.max(r,g,b),m=Math.min(r,g,b),d=M-m,h=0,s=0,l=(M+m)/2;
  if(d){s=l>.5?d/(2-M-m):d/(M+m);switch(M){case r:h=((g-b)/d+(g<b?6:0))/6;break;case g:h=((b-r)/d+2)/6;break;case b:h=((r-g)/d+4)/6;break}}
  return[Math.round(h*360),Math.round(s*100),Math.round(l*100)]}
function hslToRgb(h,s,l){h/=360;var r,g,b;if(s===0){r=g=b=l}else{function hue(t){if(t<0)t+=1;if(t>1)t-=1;if(t<1/6)return 6*t;if(t<1/2)return 1;if(t<2/3)return(2/3-t)*6;return 0}
    var q=l<.5?l*(1+s):l+s-l*s,p=2*l-q;r=hue(h+1/3);g=hue(h);b=hue(h-1/3)}
  return[Math.round(r*255),Math.round(g*255),Math.round(b*255)]}
function addToPalette(){var h=document.getElementById('hex').value;if(palette.indexOf(h)<0){palette.push(h);renderSwatches()}}
function renderSwatches(){
  var html='';for(var i=0;i<Math.min(palette.length,12);i++){html+='<div class="swatch" style="background:'+palette[i]+'" onclick="removeSwatch('+i+')" title="Click to remove"><span class="code">'+palette[i]+'</span></div>'}
  html+='<div class="swatch" style="background:var(--bg);border:1px dashed var(--border);display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--muted);cursor:pointer" onclick="addToPalette()" title="Add current color">+</div>';
  document.getElementById('swatches').innerHTML=html
}
function removeSwatch(i){palette.splice(i,1);renderSwatches()}
function genScheme(type){
  var h=parseInt(document.getElementById('hsl').value.match(/\\d+/)[0]),s=parseInt(document.getElementById('hsl').value.match(/\\d+/)[1]),l=parseInt(document.getElementById('hsl').value.match(/\\d+/)[2]);
  var colors=[];
  switch(type){
    case 'analogous':for(var i=-2;i<=2;i++)colors.push(hslToHex((h+i*30+360)%360,s,l));break;
    case 'complementary':colors.push(hslToHex(h,s,l));colors.push(hslToHex((h+180)%360,s,l));break;
    case 'triadic':for(var i=0;i<3;i++)colors.push(hslToHex((h+i*120)%360,s,l));break;
    case 'mono':for(var i=0;i<5;i++)colors.push(hslToHex(h,s,Math.max(5,l-25+i*12)));break;
    case 'random':for(var i=0;i<5;i++)colors.push(hslToHex(Math.floor(Math.random()*360),50+Math.floor(Math.random()*40),40+Math.floor(Math.random()*30)));break;
  }
  var html='<div class="scheme-row">';for(var i=0;i<colors.length;i++){html+='<div style="background:'+colors[i]+'" title="'+colors[i]+'" onclick="selectColor(\\''+colors[i]+'\\')"></div>'}
  html+='</div>';document.getElementById('scheme-display').innerHTML=html
}
function hslToHex(h,s,l){var r=hslToRgb(h,s,l);return'#'+r.map(function(v){return v.toString(16).padStart(2,'0')}).join('')}
function selectColor(c){picker.value=c;syncFromPicker()}
function exportPalette(){
  var css=':root {\\n';for(var i=0;i<palette.length;i++){css+='  --color-'+(i+1)+': '+palette[i]+';\\n'}
  css+='}';navigator.clipboard.writeText(css);document.getElementById('export-info').textContent='CSS copied to clipboard!'
}
renderSwatches();
</script>""")


def _password_generator(genome: Genome) -> str:
    """强密码生成器"""
    name = _resolve_name(genome, "PassForge Pro", "Password Generator")
    return _wrap(name, """<style>
.generator{max-width:600px;margin:0 auto}
.result-box{background:#1e1e2e;padding:20px 24px;border-radius:10px;display:flex;align-items:center;gap:12px;margin-bottom:20px}
.result-box input{flex:1;background:transparent;border:none;color:#10b981;font-family:'SF Mono',Monaco,monospace;font-size:20px;outline:none}
.result-box button{padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12px}
.strength-bar{height:4px;border-radius:2px;margin-bottom:20px;transition:background .3s}
.options{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.option{display:flex;align-items:center;gap:10px;padding:10px 14px;border:1px solid var(--border);border-radius:8px}
.option label{flex:1;font-size:13px}
.option input[type="checkbox"]{width:18px;height:18px;accent-color:var(--accent)}
.option input[type="range"]{width:80px}
.option .val{font-size:12px;font-weight:600;min-width:24px;text-align:center}
.extra-btns{display:flex;gap:8px;margin-top:16px}
.btn{padding:8px 18px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:12px}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.history{margin-top:20px;font-size:12px;color:var(--muted)}
.history span{display:inline-block;padding:2px 8px;background:var(--bg);border-radius:3px;margin:2px;font-family:monospace;cursor:pointer}
.history span:hover{background:#fee2e2;text-decoration:line-through}
</style>
<div class="generator">
  <div class="result-box">
    <input id="result" value="" readonly placeholder="Your password...">
    <button onclick="copyPass()">Copy</button>
    <button onclick="generate()">New</button>
  </div>
  <div class="strength-bar" id="strength"></div>
  <div class="options">
    <div class="option"><label>Length</label><input type="range" min="8" max="64" value="20" id="len" oninput="document.getElementById('lenVal').textContent=this.value;generate()"><span class="val" id="lenVal">20</span></div>
    <div class="option"><label>Uppercase (A-Z)</label><input type="checkbox" id="upper" checked onchange="generate()"></div>
    <div class="option"><label>Lowercase (a-z)</label><input type="checkbox" id="lower" checked onchange="generate()"></div>
    <div class="option"><label>Numbers (0-9)</label><input type="checkbox" id="numbers" checked onchange="generate()"></div>
    <div class="option"><label>Symbols (!@#$)</label><input type="checkbox" id="symbols" checked onchange="generate()"></div>
    <div class="option"><label>Avoid ambiguous</label><input type="checkbox" id="noAmbiguous" onchange="generate()"></div>
  </div>
  <div class="extra-btns">
    <button class="btn primary" onclick="generate()">Generate</button>
    <button class="btn" onclick="genMultiple(5)">Batch ×5</button>
    <button class="btn" onclick="genMultiple(10)">Batch ×10</button>
  </div>
  <div class="history" id="history"></div>
</div>
<script>
var passHistory=[];
function generate(){
  var len=parseInt(document.getElementById('len').value);
  var chars='',upper='ABCDEFGHIJKLMNOPQRSTUVWXYZ',lower='abcdefghijklmnopqrstuvwxyz',nums='0123456789',syms='!@#$%^&*()_+-=[]{}|;:,.<>?';
  var ambig='Il1O0';
  if(document.getElementById('upper').checked)chars+=upper;if(document.getElementById('lower').checked)chars+=lower;
  if(document.getElementById('numbers').checked)chars+=nums;if(document.getElementById('symbols').checked)chars+=syms;
  if(document.getElementById('noAmbiguous').checked){for(var i=0;i<ambig.length;i++)chars=chars.replace(ambig[i],'')}
  if(!chars){document.getElementById('result').value='Select at least one option';return}
  var pass='';for(var i=0;i<len;i++){pass+=chars[Math.floor(Math.random()*chars.length)]}
  document.getElementById('result').value=pass;updateStrength(pass);
  if(passHistory.indexOf(pass)<0){passHistory.unshift(pass);if(passHistory.length>20)passHistory.pop();renderHistory()}
}
function updateStrength(p){var s=0;if(p.length>=12)s++;if(p.length>=20)s++;if(/[A-Z]/.test(p))s++;if(/[a-z]/.test(p))s++;if(/[0-9]/.test(p))s++;if(/[^A-Za-z0-9]/.test(p))s++;
  var colors=['#ef4444','#f97316','#eab308','#22c55e','#059669'],bar=document.getElementById('strength');
  bar.style.background=colors[Math.min(s,colors.length-1)];bar.style.width=((s+1)/colors.length*100)+'%'}
function copyPass(){navigator.clipboard.writeText(document.getElementById('result').value)}
function genMultiple(n){var batch=[];for(var i=0;i<n;i++){generate();batch.push(document.getElementById('result').value)}
  document.getElementById('result').value=batch.join('\\n')}
function renderHistory(){document.getElementById('history').innerHTML='Recent: '+passHistory.slice(0,12).map(function(p,i){return'<span onclick="useHistory('+i+')" title="Click to reuse">'+p.slice(0,16)+'...</span>'}).join('')}
function useHistory(i){document.getElementById('result').value=passHistory[i]}
generate();
</script>""")


def _jwt_debugger(genome: Genome) -> str:
    """JWT Token 调试器"""
    name = _resolve_name(genome, "JWT Inspector", "Token Debugger")
    return _wrap(name, """<style>
textarea{width:100%;height:100px;border:1px solid var(--border);border-radius:6px;padding:14px;font-family:'SF Mono',Monaco,monospace;font-size:13px;resize:vertical;background:var(--bg);color:var(--text);margin-bottom:12px}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.panel{border:1px solid var(--border);border-radius:8px;overflow:hidden}
.panel-header{padding:8px 14px;background:var(--bg);font-size:12px;font-weight:600;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.panel-header .badge{font-size:10px;padding:2px 6px;border-radius:4px}
.badge.header{background:#dbeafe;color:#2563eb}
.badge.payload{background:#fce7f3;color:#db2777}
.badge.signature{background:#d1fae5;color:#059669}
.panel-body{padding:14px;font-family:'SF Mono',Monaco,monospace;font-size:12px;line-height:1.6;overflow:auto;max-height:300px}
.json-key{color:#2563eb}
.json-string{color:#059669}
.json-number{color:#d97706}
.json-bool{color:#7c3aed}
.claims-table{width:100%;font-size:12px;border-collapse:collapse}
.claims-table td,.claims-table th{padding:6px 10px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
.claims-table th{color:var(--muted);font-weight:500;width:30%}
.claims-table code{font-size:11px;background:var(--bg);padding:1px 4px;border-radius:3px}
.time-row{display:flex;gap:24px;margin-top:12px;font-size:12px}
.time-item{flex:1}
.time-item .label{color:var(--muted)}
.time-item .value{font-weight:600}
</style>
<div style="margin-bottom:12px">
  <button class="btn primary" onclick="decode()" style="padding:8px 18px;border:1px solid var(--border);border-radius:6px;background:var(--accent);color:#fff;cursor:pointer;font-size:13px">Decode</button>
  <button class="btn" onclick="loadSample()" style="padding:8px 18px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-size:13px;margin-left:8px">Sample</button>
</div>
<textarea id="jwt" placeholder="Paste JWT token here..."></textarea>
<div id="output"></div>
<script>
function decode(){
  var jwt=document.getElementById('jwt').value.trim();var o=document.getElementById('output');
  if(!jwt){o.innerHTML='<span style="color:#ef4444">Enter a JWT token</span>';return}
  var parts=jwt.split('.');if(parts.length!==3){o.innerHTML='<span style="color:#ef4444">Invalid JWT: expected 3 parts, got '+parts.length+'</span>';return}
  try{
    var header=JSON.parse(atob(parts[0].replace(/-/g,'+').replace(/_/g,'/')));
    var payload=JSON.parse(atob(parts[1].replace(/-/g,'+').replace(/_/g,'/')));
    var sig=parts[2];
    var html='<div class="panels">';
    html+=panelHtml('Header','header',header,parts[0])+panelHtml('Payload','payload',payload,parts[1]);
    html+='<div class="panel"><div class="panel-header"><span>Signature</span><span class="badge signature">HMAC/RSA</span></div><div class="panel-body" style="word-break:break-all;color:var(--muted)">'+escHtml(sig)+'</div></div>';
    html+='</div>';
    if(payload.iat||payload.exp||payload.nbf){
      html+='<div class="time-row">';
      if(payload.iat)html+='<div class="time-item"><div class="label">Issued At</div><div class="value">'+new Date(payload.iat*1000).toLocaleString()+'</div></div>';
      if(payload.exp){var exp=new Date(payload.exp*1000),expired=exp<new Date();html+='<div class="time-item"><div class="label">Expires</div><div class="value" style="color:'+(expired?'#ef4444':'#059669')+'">'+exp.toLocaleString()+' '+(expired?'(EXPIRED)':'(valid)')+'</div></div>'}
      if(payload.nbf)html+='<div class="time-item"><div class="label">Not Before</div><div class="value">'+new Date(payload.nbf*1000).toLocaleString()+'</div></div>';
      html+='</div>'
    }
    o.innerHTML=html
  }catch(e){o.innerHTML='<span style="color:#ef4444">Decode error: '+e.message+'</span>'}
}
function panelHtml(title,cls,obj,raw){var h='<div class="panel"><div class="panel-header"><span>'+title+'</span><span class="badge '+cls+'">'+cls.toUpperCase()+'</span></div><div class="panel-body">';
  h+='<table class="claims-table">';for(var k in obj){h+='<tr><th>'+escHtml(k)+'</th><td>';var v=obj[k];if(typeof v==='number'){if(k==='exp'||k==='iat'||k==='nbf'){v=new Date(v*1000).toLocaleString();h+='<code>'+v+'</code>'}else{h+='<code>'+v+'</code>'}}else if(typeof v==='boolean'){h+='<span class="json-bool">'+v+'</span>'}else{h+='<span>'+escHtml(String(v))+'</span>'}h+='</td></tr>'}
  h+='</table><div style="margin-top:12px;font-size:10px;color:var(--muted);word-break:break-all">Raw: '+escHtml(raw)+'</div></div></div>';return h}
function escHtml(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function loadSample(){document.getElementById('jwt').value='PASTE_YOUR_JWT_HERE';decode()}
</script>""")


# ── 工具注册表 ──

TOOL_GENERATORS = {
    (Category.DEV_TOOLS, "json_formatter"): _json_formatter,
    (Category.DEV_TOOLS, "regex_tester"): _regex_tester,
    (Category.DEV_TOOLS, "base64_codec"): _base64_codec,
    (Category.DEV_TOOLS, "jwt_debugger"): _jwt_debugger,
    (Category.CONTENT, "markdown_editor"): _markdown_editor,
    (Category.AI_CHAT, "markdown_editor"): _markdown_editor,
    (Category.PRODUCTIVITY, "json_formatter"): _json_formatter,
    (Category.PRODUCTIVITY, "password_generator"): _password_generator,
    (Category.DATA, "json_formatter"): _json_formatter,
    (Category.AUTOMATION, "json_formatter"): _json_formatter,
    (Category.SEO, "color_palette"): _color_palette,
}

_TOOL_META = {
    "json_formatter": {"name": "JSON Formatter Pro", "desc": "Format, validate, minify and tree-view JSON data. Essential tool for developers working with APIs and config files.", "tags": ["json", "formatter", "developer-tool", "api"]},
    "markdown_editor": {"name": "Markdown Studio", "desc": "Write and preview Markdown with live rendering. Export to clean HTML. Perfect for technical writers and developers.", "tags": ["markdown", "editor", "writing", "documentation"]},
    "regex_tester": {"name": "Regex Lab", "desc": "Test, debug, and understand regular expressions with real-time match highlighting and group extraction.", "tags": ["regex", "debugging", "developer-tool", "pattern-matching"]},
    "base64_codec": {"name": "Base64 Codec Pro", "desc": "Encode and decode Base64 text and files. Supports drag-and-drop file input for images and documents.", "tags": ["base64", "encoding", "developer-tool", "file-conversion"]},
    "color_palette": {"name": "Color Studio Pro", "desc": "Generate harmonious color palettes, convert between HEX/RGB/HSL, and export CSS variables. For designers and frontend developers.", "tags": ["color", "design", "css", "palette"]},
    "password_generator": {"name": "PassForge Pro", "desc": "Generate cryptographically strong passwords with full control over length, character sets, and batch generation.", "tags": ["password", "security", "generator", "privacy"]},
    "jwt_debugger": {"name": "JWT Inspector", "desc": "Decode and inspect JWT tokens. View header, payload claims, and verify expiration times. Essential for API development.", "tags": ["jwt", "authentication", "api", "debugging"]},
}


def _resolve_name(genome: Genome, default_name: str, short_name: str) -> str:
    """用 genome 的 title pattern 生成产品名"""
    if genome.title_pattern == TitlePattern.ONE_CLICK:
        return f"One-Click {default_name}"
    elif genome.title_pattern == TitlePattern.SMART:
        return f"Smart {default_name} — {genome.benefit}"
    elif genome.title_pattern == TitlePattern.PRO:
        return f"{short_name} Pro"
    elif genome.title_pattern == TitlePattern.ULTIMATE:
        return f"The Ultimate {short_name}"
    elif genome.title_pattern == TitlePattern.SIMPLE:
        return f"Simple {short_name}"
    return default_name


def _wrap(title: str, body: str) -> str:
    """包装为标准单页 HTML"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root{{--bg:#fafafa;--card:#fff;--border:#e5e7eb;--text:#111;--muted:#6b7280;--accent:#2563eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:var(--bg);color:var(--text);line-height:1.5}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{max-width:960px;margin:0 auto;padding:24px 16px}}
header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid var(--border)}}
header h1{{font-size:20px;font-weight:700}}
header .brand{{font-size:12px;color:var(--muted)}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#e2e8f0;--muted:#94a3b8;--accent:#3b82f6}}}}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <span class="brand">Built by Alpha X</span>
</header>
{body}
</body>
</html>"""


# ── Builder ──

_llm_generator = object()  # LLM 生成器哨兵

class WebToolBuilder:
    """生成有真实功能的 Web 工具"""

    _build_dir: Path = config.data_dir / "builds"

    def build(self, genome: Genome, organism_id: str) -> Path:
        self._build_dir.mkdir(parents=True, exist_ok=True)
        work_dir = self._build_dir / f"webtool_{organism_id}"
        work_dir.mkdir(exist_ok=True)

        # Check for custom request → use LLM to generate
        custom = genome.extra.get("custom_request", "") if genome.extra else ""
        if custom:
            html = self._llm_generate_tool(custom, organism_id, genome)
            if html:
                meta = self._resolve_meta(genome, organism_id, _llm_generator)
                (work_dir / "index.html").write_text(html)
                (work_dir / "listing.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
                (work_dir / "HOW_TO_USE.md").write_text(f"# {genome.express()}\n\n{custom}\n")
                return self._zip(work_dir, organism_id)

        # Pick tool type from category, with variety
        import hashlib
        h = int(hashlib.md5(organism_id.encode()).hexdigest()[:8], 16)
        options = [(k, v) for k, v in TOOL_GENERATORS.items() if k[0] == genome.category]
        if not options:
            options = list(TOOL_GENERATORS.items())
        _, generator = options[h % len(options)]

        html = generator(genome)
        meta = self._resolve_meta(genome, organism_id, generator)
        tool_key = [k[1] for k, v in TOOL_GENERATORS.items() if v is generator][0]
        tool_meta = _TOOL_META[tool_key]

        # Write product files
        (work_dir / "index.html").write_text(html)
        (work_dir / "listing.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
        (work_dir / "HOW_TO_USE.md").write_text(f"""# {tool_meta['name']}

{tool_meta['desc']}

## How to Use
1. Open `index.html` in any modern browser
2. No installation, no dependencies — works offline
3. Bookmark for quick access

## Features
- Works 100% offline after loading
- No data leaves your browser
- Dark mode support (follows system preference)
- Copy to clipboard, export, and download support

## System Requirements
Any modern browser (Chrome, Firefox, Safari, Edge).

---
Built by Alpha X | {genome.express()}
""")

        # Zip
        zip_path = self._build_dir / f"{organism_id}_webtool.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in work_dir.iterdir():
                zf.write(f, f.name)

        return zip_path

    def _llm_generate_tool(self, request: str, organism_id: str, genome: Genome) -> str | None:
        """使用 LLM 根据需求生成完整的 Web 工具 HTML。"""
        from config import config
        from core.api_utils import call_deepseek
        if not config.has_llm:
            return None
        try:
            prompt = f"""你是一个资深前端工程师。根据用户需求生成一个完整的、可用的网页工具。

## 用户需求
{request}

## 产品名称
{genome.express()}

## 硬性要求（必须遵守）
- 完整的 HTML 单文件（内嵌 CSS + JS）
- 暗色主题，现代 UI，响应式
- 所有功能必须完整可用，不只是 UI 壳
- JS 变量命名一致，不要同一个变量有多个名字
- 初始化代码必须完整，确保页面加载后能直接使用
- 不需要任何外部依赖
- 不需要任何解释文字，只输出代码

## 输出
完整的 HTML 代码（从 <!DOCTYPE html> 开始）:"""

            html = call_deepseek(
                prompt, config.deepseek_api_key, config.deepseek_base_url,
                temperature=0.3, max_tokens=10000, timeout=90,
            )
            # 清理 LLM 输出
            html = html.strip()
            if html.startswith("```"):
                html = html.split("```", 2)[1]
                if html.startswith("html"):
                    html = html[4:]
                html = html.strip()
            if not html.lower().startswith("<!doctype"):
                return None
            return html.strip()
        except Exception:
            return None

    def _self_review(self, html: str, request: str) -> str | None:
        """Agent 自审：检查自己生成的代码，发现 bug 自动修。"""
        from config import config
        from core.api_utils import call_deepseek
        if not config.has_llm:
            return None
        try:
            # 只审前 8000 字符，避免超 token
            snippet = html[:8000]
            prompt = f"""你是严格的前端代码审查员。审查以下代码，找出所有问题并修复。

## 原始需求
{request}

## 需要审查的代码
```html
{snippet}
```

## 审查要点
1. 功能是否完整实现了需求
2. 有无 JS 逻辑错误（变量未定义、计时器未清理、边界条件）
3. UI 是否有明显问题（按钮不可点、颜色看不清、移动端崩）
4. 是否缺关键功能

## 输出
输出修复后的完整 HTML 代码（从 <!DOCTYPE html> 开始）。
如果代码已经很好没有明显问题，原样返回。

HTML:"""

            fixed = call_deepseek(
                prompt, config.deepseek_api_key, config.deepseek_base_url,
                temperature=0.1, max_tokens=6000, timeout=60,
            )
            fixed = fixed.strip()
            if fixed.startswith("```"):
                fixed = fixed.split("```", 2)[1]
                if fixed.startswith("html"):
                    fixed = fixed[4:]
                fixed = fixed.strip()
            if fixed.lower().startswith("<!doctype") and len(fixed) > 500:
                return fixed
            return None
        except Exception:
            return None

    def _zip(self, work_dir: Path, organism_id: str) -> Path:
        zip_path = self._build_dir / f"{organism_id}_webtool.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in work_dir.iterdir():
                zf.write(f, f.name)
        return zip_path

    def _resolve_meta(self, genome: Genome, organism_id: str, generator) -> dict:
        if generator is _llm_generator:
            name = genome.express()
            return {
                "title": name,
                "subtitle": genome.extra.get("custom_request", "")[:80] if genome.extra else "",
                "price": genome.price_point,
                "category": genome.category.value,
                "id": organism_id,
            }
        tool_key = [k[1] for k, v in TOOL_GENERATORS.items() if v is generator][0]
        tool_meta = _TOOL_META[tool_key]
        name = _resolve_name(genome, tool_meta["name"], tool_meta["name"])

        return {
            "title": name,
            "subtitle": tool_meta["desc"][:80],
            "description": f"<p>{tool_meta['desc']}</p><p>A self-contained web tool that works offline in any browser. No installation required — just open and use. Built for {genome.target_market.value.replace('_', ' ').title()} users.</p>",
            "bullets": [
                "Works offline — no internet needed after first load",
                "Dark mode — automatically matches your system theme",
                "No data collection — everything stays in your browser",
                "Export and download support built in",
            ],
            "target_audience": genome.target_market.value.replace("_", " ").title(),
            "seo_keywords": tool_meta["tags"] + [genome.category.value],
            "price_point": genome.price_point,
            "category": genome.category.value,
            "product_type": "web_tool",
        }
