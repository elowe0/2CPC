"""Project dashboard: .2cpc/index.html (every plan, version, status, todos, saved answers, live progress)."""
import json
from pathlib import Path

from .markdown import esc, inline
from .parser import parse

ORDER = {"active": 0, "draft": 1, "done": 2, "archived": 3}
LABEL = {"active": "actif", "draft": "brouillon", "done": "fait", "archived": "archivé"}

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2129;--muted:#667085;--line:#e3e6eb;--accent:#3b6fe0;
--active:#0ca30c;--draft:#c98500;--done:#6250d6;--archived:#98a2b3;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#14161a;--card:#1d2026;--text:#e6e8eb;--muted:#98a2b3;--line:#2c3038;
--accent:#7aa2ff;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:1.4rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px;font-size:.9rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:6px}
.card h2{font-size:1rem;margin:0}.card h2 a{color:inherit;text-decoration:none}.card h2 a:hover{color:var(--accent)}
.meta{color:var(--muted);font-size:.82rem;display:flex;flex-wrap:wrap;gap:4px 10px}
.st{font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;padding:1px 8px;border-radius:999px;color:#fff}
.st-active{background:var(--active)}.st-draft{background:var(--draft)}.st-done{background:var(--done)}.st-archived{background:var(--archived)}
.bar{height:6px;border-radius:3px;background:var(--line);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.row{font-size:.85rem;display:flex;justify-content:space-between;gap:8px}.row span:first-child{color:var(--muted)}
.vers a,.vers span{font-size:.8rem;margin-right:6px;color:var(--accent)}.vers span{color:var(--muted);text-decoration:line-through}
details.arch{margin-top:22px}details.arch summary{cursor:pointer;color:var(--muted)}
.card.archived{opacity:.7}
"""

JS = """
(function(){document.querySelectorAll('[data-key]').forEach(function(el){
 var s=null;try{s=JSON.parse(localStorage.getItem(el.dataset.key)||'null')}catch(e){}
 var tot=+el.dataset.total;if(!s||!s.a||!tot)return;
 var n=Object.keys(s.a).filter(function(k){var v=s.a[k];return v!==''&&v!=null&&!(Array.isArray(v)&&!v.length)&&!(typeof v==='object'&&!Array.isArray(v)&&!Object.keys(v).length)}).length;
 n=Math.min(n,tot);el.hidden=false;el.querySelector('b').textContent=n+'/'+tot;el.querySelector('i').style.width=(100*n/tot)+'%';
});})();
"""


def card(root, pid, e, load_state, storage_key):
    pdir = root / ".2cpc" / pid
    v = e["v"]
    src = pdir / f"v{v}" / "plan.txt"
    plan = parse(src.read_bytes().decode("utf-8-sig")) if src.is_file() else None
    st = e.get("status") or "active"
    qs = [q for q in (plan.questions if plan else []) if q["qt"] != "todo"]
    todos = [(q["id"], k) for q in (plan.questions if plan else []) if q["qt"] == "todo" for k in q["keys"]]
    done = load_state(root, pid).get("todo", {})
    nd = sum(1 for q, k in todos if f"{q}.{k}" in done)
    saved = next((k for k in range(v, 0, -1) if (pdir / f"v{k}" / "answers.txt").is_file()), None)
    rows = []
    if todos:
        rows.append(f'<div class="row"><span>Todos (agent)</span><span>{nd}/{len(todos)}</span></div>'
                    f'<div class="bar"><i style="width:{100 * nd / len(todos):.0f}%"></i></div>')
    rows.append(f'<div class="row"><span>Réponses enregistrées</span><span>{f"v{saved}" if saved else "—"}</span></div>')
    if qs:
        rows.append(f'<div data-key="{esc(storage_key(root, pid, v))}" data-total="{len(qs)}" hidden>'
                    f'<div class="row"><span>Réponses v{v} (ce navigateur)</span><b></b></div>'
                    f'<div class="bar"><i></i></div></div>')
    vers = "".join(
        f'<a href="{esc(pid)}/v{k}/index.html">v{k}</a>' if (pdir / f"v{k}" / "index.html").is_file()
        else f'<span title="gc">v{k}</span>' for k in sorted(int(x) for x in e["versions"]))
    href = f"{pid}/v{v}/index.html"
    return (f'<article class="card {st}"><h2><a href="{esc(href)}">{inline(e["title"])}</a></h2>'
            f'<div class="meta"><span class="st st-{st}">{LABEL.get(st, st)}</span><span>v{v}</span>'
            f'<span>{esc(e.get("updated", "")[:10])}</span><code>{esc(pid)}</code></div>'
            f'{"".join(rows)}<div class="vers">{vers}</div></article>')


def write_dashboard(root, idx, load_state, storage_key):
    root = Path(root)
    plans = sorted(idx["plans"].items(), key=lambda kv: kv[1].get("updated", ""), reverse=True)
    plans.sort(key=lambda kv: ORDER.get(kv[1].get("status") or "active", 0))
    live = [card(root, p, e, load_state, storage_key) for p, e in plans if e.get("status") != "archived"]
    arch = [card(root, p, e, load_state, storage_key) for p, e in plans if e.get("status") == "archived"]
    body = f'<div class="grid">{"".join(live)}</div>'
    if arch:
        body += f'<details class="arch"><summary>Archivés ({len(arch)})</summary><div class="grid">{"".join(arch)}</div></details>'
    if not plans:
        body = "<p>Aucun plan.</p>"
    page = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="generator" content="2CPC">'
            f'<title>Plans 2CPC · {esc(root.name)}</title><style>{CSS}</style></head><body><main>'
            f'<h1>Plans 2CPC · {esc(root.name)}</h1><p class="sub">{len(plans)} plan(s) · <code>{esc(str(root))}</code></p>'
            f'{body}</main><script>{JS}</script></body></html>')
    out = root / ".2cpc" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
