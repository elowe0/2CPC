"""Project dashboard: .2cpc/index.html — every plan with its icon, status, todos, saved answers and live progress.

Interactive but static (file://): sorting / filters / view are kept in localStorage; status changes are applied
on screen at once and queued as one `cpc.py apply "status <id> <value> ; …"` command to copy (terminal or Claude).
"""
import base64
import json
from pathlib import Path

from .icons import icon_png
from .markdown import esc
from .motifs import MOTIFS
from .parser import parse

STATUSES = ("active", "draft", "done", "archived")

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2129;--muted:#667085;--line:#e3e6eb;--accent:#3b6fe0;--soft:#eef2fb;
--active:#0ca30c;--draft:#c98500;--done:#6250d6;--archived:#98a2b3;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1d2026;--text:#e6e8eb;--muted:#98a2b3;--line:#2c3038;
--accent:#7aa2ff;--soft:#232a38;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.dash-ico{width:36px;height:36px;image-rendering:pixelated;vertical-align:middle;margin-right:10px;border-radius:5px}
main{max-width:1180px;margin:0 auto;padding:24px 16px 90px}h1{font-size:1.4rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 16px;font-size:.9rem}
.tools{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin-bottom:16px}
.tools input[type=search],.tools select{font:inherit;font-size:.88rem;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text)}
.tools input[type=search]{flex:1;min-width:180px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:inherit;font-size:.8rem;padding:4px 10px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--muted);cursor:pointer}
.chip[aria-pressed=true]{background:var(--soft);border-color:var(--accent);color:var(--text)}
.chip .n{opacity:.7;margin-left:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;display:grid;grid-template-columns:64px 1fr;gap:6px 14px;align-items:start}
.card .ico{width:64px;height:64px;image-rendering:pixelated;grid-row:span 3;border-radius:6px}
.card h2{font-size:1rem;margin:0;line-height:1.3}.card h2 a{color:inherit;text-decoration:none}.card h2 a:hover{color:var(--accent)}
.meta{color:var(--muted);font-size:.8rem;display:flex;flex-wrap:wrap;gap:4px 10px;align-items:center}
.meta code{font-size:.75rem}
.st{font:inherit;font-size:.72rem;font-weight:600;padding:2px 6px;border-radius:999px;border:1px solid transparent;color:#fff;cursor:pointer}
.st-active{background:var(--active)}.st-draft{background:var(--draft)}.st-done{background:var(--done)}.st-archived{background:var(--archived)}
.st.changed{outline:2px dashed var(--accent);outline-offset:2px}
.info{grid-column:1/-1;display:flex;flex-direction:column;gap:5px}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.row{font-size:.82rem;display:flex;justify-content:space-between;gap:8px}.row span:first-child{color:var(--muted)}
.row .pend{color:var(--draft);font-weight:600}
.vers a,.vers span{font-size:.78rem;margin-right:6px;color:var(--accent)}.vers span{color:var(--muted);text-decoration:line-through}
.list .grid{grid-template-columns:1fr;gap:6px}
.list .card{grid-template-columns:32px 1fr auto;padding:8px 12px;align-items:center}
.list .card .ico{width:32px;height:32px;grid-row:auto}
.list .info{grid-column:auto;flex-direction:row;gap:14px;align-items:center}.list .info .bar,.list .vers{display:none}
.card.archived{opacity:.65}
.empty{color:var(--muted);padding:30px 0;text-align:center}
#pending{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);background:var(--card);border:1px solid var(--accent);
border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.18);padding:10px 14px;display:flex;gap:10px;align-items:center;max-width:calc(100% - 32px);flex-wrap:wrap}
#pending[hidden]{display:none}
#pending code{font-size:.75rem;word-break:break-all;max-width:520px}
.btn{font:inherit;font-size:.85rem;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--text);cursor:pointer}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
"""

JS = r"""
(function(){
var D=window.DASH, KEY='2cpc-dash:'+D.root, ST={sort:'upd',view:'grid',st:{},q:'',pend:false,todo:false,icon:'',over:{}};
try{var o=JSON.parse(localStorage.getItem(KEY)||'null');if(o)for(var k in o)ST[k]=o[k]}catch(e){}
var L={active:'actif',draft:'brouillon',done:'fait',archived:'archivé'};
var $=function(s,r){return (r||document).querySelector(s)};
function save(){try{localStorage.setItem(KEY,JSON.stringify(ST))}catch(e){}}
function fold(s){return String(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'')}
// drop queued changes that the files already reflect (after `cpc.py apply`)
D.plans.forEach(function(p){if(ST.over[p.id]===p.status)delete ST.over[p.id]});
Object.keys(ST.over).forEach(function(id){if(!D.plans.some(function(p){return p.id===id}))delete ST.over[id]});
function status(p){return ST.over[p.id]||p.status}
function progress(p){
 if(!p.qTotal)return null;var s=null;try{s=JSON.parse(localStorage.getItem(p.key)||'null')}catch(e){}
 if(!s||!s.a)return 0;
 var n=Object.keys(s.a).filter(function(k){var v=s.a[k];return v!==''&&v!=null&&!(Array.isArray(v)&&!v.length)&&!(typeof v==='object'&&!Array.isArray(v)&&!Object.keys(v).length)}).length;
 return Math.min(n,p.qTotal);
}
D.plans.forEach(function(p){p.prog=progress(p)});
var SORTS={upd:function(a,b){return b.updated.localeCompare(a.updated)},created:function(a,b){return b.created.localeCompare(a.created)},
 title:function(a,b){return a.title.localeCompare(b.title,'fr')},status:function(a,b){return D.order.indexOf(status(a))-D.order.indexOf(status(b))||b.updated.localeCompare(a.updated)},
 prog:function(a,b){return ((a.prog||0)/(a.qTotal||1))-((b.prog||0)/(b.qTotal||1))},
 todo:function(a,b){return (b.todoTotal-b.todoDone)-(a.todoTotal-a.todoDone)}};
function el(tag,cls,txt){var e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e}
function row(label,val,cls){var r=el('div','row');r.appendChild(el('span',null,label));var v=el('span',cls,val);r.appendChild(v);return r}
function bar(f){var b=el('div','bar'),i=el('i');i.style.width=Math.round(100*f)+'%';b.appendChild(i);return b}
function card(p){
 var s=status(p),c=el('article','card '+s);
 var img=el('img','ico');img.src=p.icon;img.alt=p.motif;img.title=p.motif+(p.family?' · '+p.family:'');c.appendChild(img);
 var h=el('h2'),a=el('a',null,p.title);a.href=p.href;h.appendChild(a);c.appendChild(h);
 var m=el('div','meta'),sel=el('select','st st-'+s+(ST.over[p.id]?' changed':''));
 D.order.forEach(function(v){var o=el('option',null,L[v]);o.value=v;o.selected=v===s;sel.appendChild(o)});
 sel.title='Statut (appliqué avec la commande copiée)';
 sel.onchange=function(){if(sel.value===p.status)delete ST.over[p.id];else ST.over[p.id]=sel.value;save();draw()};
 m.appendChild(sel);m.appendChild(el('span',null,'v'+p.v));m.appendChild(el('span',null,p.updated.slice(0,10)));m.appendChild(el('code',null,p.id));c.appendChild(m);
 var info=el('div','info');
 if(p.todoTotal){info.appendChild(row('Todos (agent)',p.todoDone+'/'+p.todoTotal));info.appendChild(bar(p.todoDone/p.todoTotal))}
 info.appendChild(row('Réponses enregistrées',p.saved?('v'+p.saved):'—',p.pending?'pend':null));
 if(p.qTotal){info.appendChild(row('Réponses v'+p.v+' (ce navigateur)',(p.prog||0)+'/'+p.qTotal));info.appendChild(bar((p.prog||0)/p.qTotal))}
 var vs=el('div','vers');p.versions.forEach(function(v){var x;if(v.ok){x=el('a',null,'v'+v.v);x.href=v.href}else{x=el('span',null,'v'+v.v);x.title='supprimée par gc'}vs.appendChild(x)});info.appendChild(vs);
 c.appendChild(info);return c;
}
function chips(){
 var box=$('#stChips');box.innerHTML='';
 D.order.forEach(function(v){var n=D.plans.filter(function(p){return status(p)===v}).length;
  var b=el('button','chip',L[v]);b.type='button';b.setAttribute('aria-pressed',!!ST.st[v]);b.appendChild(el('span','n',String(n)));
  b.onclick=function(){ST.st[v]=!ST.st[v];save();draw()};box.appendChild(b)});
 [['pend','Réponses en attente'],['todo','Todos restants']].forEach(function(f){
  var b=el('button','chip',f[1]);b.type='button';b.setAttribute('aria-pressed',!!ST[f[0]]);b.onclick=function(){ST[f[0]]=!ST[f[0]];save();draw()};box.appendChild(b)});
}
function visible(p){
 var any=D.order.some(function(v){return ST.st[v]});
 if(any?!ST.st[status(p)]:status(p)==='archived')return false;
 if(ST.pend&&!p.pending)return false;
 if(ST.todo&&!(p.todoTotal>p.todoDone))return false;
 if(ST.icon&&p.motif!==ST.icon)return false;
 if(ST.q){var q=fold(ST.q);if((fold(p.title)+' '+fold(p.id)+' '+fold(p.motif)+' '+fold(p.family)).indexOf(q)<0)return false}
 return true;
}
function command(){
 var ops=Object.keys(ST.over).map(function(id){return 'status '+id+' '+ST.over[id]});
 return ops.length?'python "'+D.tool+'" --root "'+D.root+'" apply "'+ops.join(' ; ')+'"':'';
}
function draw(){
 chips();
 var list=D.plans.filter(visible).sort(SORTS[ST.sort]||SORTS.upd),g=$('#grid');g.innerHTML='';
 list.forEach(function(p){g.appendChild(card(p))});
 $('#empty').hidden=!!list.length;
 $('#count').textContent=list.length+' / '+D.plans.length+' plan(s)'+(D.order.some(function(v){return ST.st[v]})?'':' · archivés masqués');
 document.body.classList.toggle('list',ST.view==='list');
 var cmd=command(),pb=$('#pending');pb.hidden=!cmd;
 $('#pendTxt').textContent=Object.keys(ST.over).length+' changement(s) de statut à appliquer :';$('#pendCmd').textContent=cmd;
}
function copy(t){
 function ok(){$('#copyBtn').textContent='Copié !';setTimeout(function(){$('#copyBtn').textContent='Copier la commande'},1800)}
 function fb(){var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();var r=false;try{r=document.execCommand('copy')}catch(e){}ta.remove();if(r)ok();else window.prompt('Copiez :',t)}
 if(navigator.clipboard&&window.isSecureContext!==false)navigator.clipboard.writeText(t).then(ok,fb);else fb();
}
var sortSel=$('#sort'),iconSel=$('#icon'),q=$('#q');
sortSel.value=ST.sort;sortSel.onchange=function(){ST.sort=sortSel.value;save();draw()};
D.motifs.forEach(function(m){var o=el('option',null,m.name+' ('+m.n+')');o.value=m.name;iconSel.appendChild(o)});
iconSel.value=ST.icon;iconSel.onchange=function(){ST.icon=iconSel.value;save();draw()};
q.value=ST.q;q.oninput=function(){ST.q=q.value;save();draw()};
$('#view').onclick=function(){ST.view=ST.view==='list'?'grid':'list';save();draw()};
$('#copyBtn').onclick=function(){copy(command())};
$('#undoBtn').onclick=function(){ST.over={};save();draw()};
draw();
})();
"""


def plan_data(root, pid, e, load_state, storage_key):
    pdir = root / ".2cpc" / pid
    v = e["v"]
    src = pdir / f"v{v}" / "plan.txt"
    plan = parse(src.read_bytes().decode("utf-8-sig")) if src.is_file() else None
    state = load_state(root, pid)
    qs = [q for q in (plan.questions if plan else []) if q["qt"] != "todo"]
    todos = [(q["id"], k) for q in (plan.questions if plan else []) if q["qt"] == "todo" for k in q["keys"]]
    done = state.get("todo", {})
    saved = next((k for k in range(v, 0, -1) if (pdir / f"v{k}" / "answers.txt").is_file()), None)
    motif = state.get("icon") or "creature"
    versions = sorted(int(x) for x in e["versions"])
    return {
        "id": pid, "title": e["title"], "status": e.get("status") or "active", "v": v,
        "updated": e.get("updated", ""), "created": e["versions"].get("1", {}).get("date", e.get("updated", "")),
        "href": f"{pid}/v{v}/index.html", "icon": f"{pid}/icon.png" if (pdir / "icon.png").is_file() else "",
        "motif": motif, "family": MOTIFS.get(motif, {}).get("fam", ""),
        "todoTotal": len(todos), "todoDone": sum(1 for q, k in todos if f"{q}.{k}" in done),
        "saved": saved, "qTotal": len(qs), "pending": bool(qs) and saved != v,
        "key": storage_key(root, pid, v),
        "versions": [{"v": k, "ok": (pdir / f"v{k}" / "index.html").is_file(), "href": f"{pid}/v{k}/index.html"}
                     for k in versions],
    }


def write_dashboard(root, idx, load_state, storage_key, tool=""):
    root = Path(root)
    plans = [plan_data(root, pid, e, load_state, storage_key) for pid, e in idx["plans"].items()]
    counts = {}
    for p in plans:
        counts[p["motif"]] = counts.get(p["motif"], 0) + 1
    data = {"root": root.as_posix(), "tool": tool, "order": list(STATUSES), "plans": plans,
            "motifs": [{"name": k, "n": n} for k, n in sorted(counts.items())]}
    js_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    # dashboard icon: "pie" motif, colors from the project name (inline PNG: favicon + title)
    png = icon_png(f"2cpc-dashboard:{root.name}", "", motif="pie")[1]
    ico = "data:image/png;base64," + base64.b64encode(png).decode()
    (root / ".2cpc").mkdir(parents=True, exist_ok=True)
    (root / ".2cpc" / "dashboard.png").write_bytes(png)  # used by the "dashboard" button of every plan page
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="generator" content="2CPC">
<title>Plans 2CPC · {esc(root.name)}</title><link rel="icon" type="image/png" href="{ico}">
<style>{CSS}</style></head><body><main>
<h1><img class="dash-ico" src="{ico}" alt="" width="36" height="36">Plans 2CPC · {esc(root.name)}</h1><p class="sub"><span id="count"></span> · <code>{esc(str(root))}</code></p>
<div class="tools">
 <input type="search" id="q" placeholder="Rechercher (titre, id, motif)…">
 <select id="sort" title="Tri"><option value="upd">Dernière mise à jour</option><option value="created">Date de création</option>
 <option value="title">Titre</option><option value="status">Statut</option><option value="prog">Avancement des réponses</option>
 <option value="todo">Todos restants</option></select>
 <select id="icon" title="Motif d'icône"><option value="">Tous les motifs</option></select>
 <button type="button" class="btn" id="view" title="Grille / liste">▦ / ☰</button>
 <div class="chips" id="stChips"></div>
</div>
<div class="grid" id="grid"></div><p class="empty" id="empty" hidden>Aucun plan ne correspond.</p>
</main>
<div id="pending" hidden><span id="pendTxt"></span><code id="pendCmd"></code>
 <button type="button" class="btn primary" id="copyBtn">Copier la commande</button><button type="button" class="btn" id="undoBtn">Annuler</button></div>
<script>window.DASH={js_json};</script><script>{JS}</script></body></html>"""
    out = root / ".2cpc" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
