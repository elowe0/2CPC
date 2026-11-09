(function () {
  "use strict";
  var P = window.PLAN, I = window.I18N;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var Q = {}; P.questions.forEach(function (q) { Q[q.id] = q; });

  // ---------- storage ----------
  function load(k) {
    if (!k) return null;
    try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; }
  }
  var S = load(P.key);
  var fresh = !S;
  S = S || {};
  S.a = S.a || {}; S.c = S.c || {}; S.r = S.r || {}; S.o = S.o || {};
  var A = window.CPCAnswers, OTHER = A.OTHER;  // answers.js (pure answer-text functions)

  function save() {
    S.ts = new Date().toISOString();
    var el = $("#saveState");
    try {
      localStorage.setItem(P.key, JSON.stringify(S));
      var d = new Date();
      el.textContent = t("saved") + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
      el.classList.remove("fail");
    } catch (e) {
      el.textContent = t("saveFail");
      el.classList.add("fail");
    }
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  // ---------- i18n ----------
  var lang = (function () {
    var saved; try { saved = localStorage.getItem("2cpc:lang"); } catch (e) {}
    if (saved && I[saved]) return saved;
    if (P.lang && I[P.lang]) return P.lang;
    return (navigator.language || "fr").slice(0, 2) === "fr" ? "fr" : "en";
  })();
  function t(k, vars) {
    var s = (I[lang] && I[lang][k]) || I.en[k] || k;
    if (vars) Object.keys(vars).forEach(function (v) { s = s.split("{" + v + "}").join(vars[v]); });
    return s;
  }
  function applyLang() {
    document.documentElement.lang = lang;
    $$("[data-i18n]").forEach(function (e) { e.textContent = t(e.getAttribute("data-i18n")); });
    $$("[data-i18n-ph]").forEach(function (e) { e.placeholder = t(e.getAttribute("data-i18n-ph")); });
    $$("[data-i18n-title]").forEach(function (e) { e.title = t(e.getAttribute("data-i18n-title")); });
    $$(".langs button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.lang === lang); });
    var pv = prevV();
    $$(".badge.reused").forEach(function (b) { b.textContent = t("reused", { v: pv }); });
    $("#reusedBanner div").textContent = t("reusedBanner", { v: pv });
    if (S.ts) save(); else $("#saveState").textContent = "";
    $$(".next-list li.custom").forEach(nxTitles);
    $$("figure.mermaid-wrap figcaption").forEach(function (e) { e.textContent = t("mermaidOffline"); });
    if (typeof chgLabels === "function" && chgBar !== undefined) chgLabels();
    refresh();
  }
  function prevV() { return P.v - 1; }

  // ---------- carry-over from previous version ----------
  // map an option key from a previous version (e.g. full label "BLD-01 Citadelle (P1)") to a current key
  function remap(q, old) {
    var opts = q.opts || [];
    if (opts.indexOf(old) >= 0) return old;
    old = String(old);
    for (var i = 0; i < opts.length; i++) {
      var k = opts[i], L = (q.labels && q.labels[k]) || k;
      if (old === L || old.indexOf(k + " ") === 0 || old.indexOf(k + "=") === 0 ||
          (L.length > 3 && old.slice(-L.length - 1) === " " + L)) return k;
    }
    return old;
  }
  function remapAll(q, v) {
    if (!q.opts) return v;
    if (Array.isArray(v)) return v.map(function (x) { return remap(q, x); });
    if (q.qt === "approve" && v && typeof v === "object") {
      var o = {}; Object.keys(v).forEach(function (k) { o[remap(q, k)] = v[k]; }); return o;
    }
    return typeof v === "string" ? remap(q, v) : v;
  }
  function compat(q, v) {
    if (v === undefined || v === null) return undefined;
    v = remapAll(q, v);
    var opts = q.opts || [];
    switch (q.qt) {
      case "choice": case "pick": return opts.indexOf(v) >= 0 || (v === OTHER && q.other) ? v : undefined;
      case "yesno": return v === "yes" || v === "no" ? v : undefined;
      case "scale": var n = +v; return n >= q.min && n <= q.max ? String(n) : undefined;
      case "multi": var m = (v || []).filter(function (x) { return opts.indexOf(x) >= 0 || (x === OTHER && q.other); }); return m.length ? m : undefined;
      case "todo": var td = (v || []).filter(function (x) { return (q.items || []).indexOf(x) >= 0; }); return td.length ? td : undefined;
      case "rank":
        if (!Array.isArray(v)) return undefined;
        var r = v.filter(function (x) { return opts.indexOf(x) >= 0; });
        opts.forEach(function (x) { if (r.indexOf(x) < 0) r.push(x); });
        return r;
      case "approve":
        var o = {}, any = false;
        Object.keys(v || {}).forEach(function (k) { if (opts.indexOf(k) >= 0) { o[k] = v[k]; any = true; } });
        return any ? o : undefined;
      case "matrix":
        var mx = {}, ok = false;
        Object.keys(v || {}).forEach(function (k) {
          if ((q.rows || []).indexOf(k) >= 0 && (q.cols || []).indexOf(v[k]) >= 0) { mx[k] = v[k]; ok = true; }
        });
        return ok ? mx : undefined;
      default: return typeof v === "string" && v ? v : undefined;
    }
  }
  if (fresh && P.prevKey) {
    var prev = load(P.prevKey);
    if (prev && prev.a) {
      P.questions.forEach(function (q) {
        var pq = prev.a[q.id], v = compat(q, pq);
        if (v !== undefined) {
          S.a[q.id] = v; S.r[q.id] = 1;
          if (q.other && prev.o && prev.o[q.id]) S.o[q.id] = prev.o[q.id];
        }
      });
      if (Object.keys(S.r).length) save();
    }
  }

  if (fresh) {
    var anyDef = false;
    P.questions.forEach(function (q) {
      if (q.def !== undefined && S.a[q.id] === undefined) { S.a[q.id] = q.def; anyDef = true; }
    });
  }

  // todo items done by the agent (`cpc.py todo`) always count as checked
  P.questions.forEach(function (q) {
    if (q.qt !== "todo" || !(q.agent || []).length) return;
    var cur = Array.isArray(S.a[q.id]) ? S.a[q.id] : [];
    S.a[q.id] = q.items.filter(function (x) { return cur.indexOf(x) >= 0 || q.agent.indexOf(x) >= 0; });
  });

  // ---------- "What next?" panel ----------
  // S.n = { items: [{k: key} | {c: custom text}, each with on: bool], pause: bool, note: str }
  var NX = P.next, nxBox = $("#next");
  function nxInit() {
    var opts = NX.opts, st = S.n && Array.isArray(S.n.items) ? S.n : null, items = [], seen = {};
    if (st) st.items.forEach(function (it) {
      if (it.c) items.push({ c: String(it.c), on: !!it.on });
      else if (opts.indexOf(it.k) >= 0 && !seen[it.k]) { seen[it.k] = 1; items.push({ k: it.k, on: !!it.on }); }
    });
    opts.forEach(function (k) { if (!seen[k]) items.push({ k: k, on: !st && (NX.rec || []).indexOf(k) >= 0 }); });
    S.n = { items: items, pause: !!(st && st.pause), note: (st && st.note) || "" };
  }
  function nxTitles(li) {
    li.querySelector(".up").title = t("up"); li.querySelector(".down").title = t("down");
    li.querySelector(".del").title = t("nextDel");
  }
  function nxCustomLi(txt) {
    var li = document.createElement("li");
    li.draggable = true; li.className = "custom"; li.dataset.c = txt;
    li.innerHTML = '<span class="grip" aria-hidden="true">⋮⋮</span><input type="checkbox"><span class="rk"></span>' +
      '<span class="lbl"><span class="ol"><span class="lt"></span></span></span>' +
      '<button type="button" class="up">↑</button><button type="button" class="down">↓</button>' +
      '<button type="button" class="del">×</button>';
    $(".lt", li).textContent = txt;
    $("input", li).setAttribute("aria-label", txt);
    nxTitles(li);
    return li;
  }
  function nxWrite() {
    var ol = $(".next-list", nxBox), lis = {};
    $$("li[data-k]", ol).forEach(function (li) { lis[li.dataset.k] = li; });
    $$("li.custom", ol).forEach(function (li) { li.remove(); });
    S.n.items.forEach(function (it) {
      var li = it.c ? nxCustomLi(it.c) : lis[it.k];
      if (!li) return;
      $("input", li).checked = it.on; ol.appendChild(li);
    });
    $(".next-pause input", nxBox).checked = S.n.pause;
    $(".next-note", nxBox).value = S.n.note;
    nxNums();
  }
  function nxRead() {
    S.n.items = $$(".next-list li", nxBox).map(function (li) {
      var on = $("input", li).checked;
      return li.dataset.c !== undefined ? { c: li.dataset.c, on: on } : { k: li.dataset.k, on: on };
    });
    S.n.pause = $(".next-pause input", nxBox).checked;
    S.n.note = $(".next-note", nxBox).value;
  }
  function nxNums() {
    var n = 0;
    $$(".next-list li", nxBox).forEach(function (li) {
      var on = $("input", li).checked;
      li.classList.toggle("off", !on);
      $(".rk", li).textContent = on ? ++n + "." : "";
    });
    $(".next-none", nxBox).hidden = n > 0;
  }
  function nxChanged() { nxRead(); nxNums(); save(); }
  function nxAdd() {
    var inp = $(".next-new", nxBox), v = inp.value.trim();
    if (!v) { inp.focus(); return; }
    var li = nxCustomLi(v); $("input", li).checked = true;
    $(".next-list", nxBox).appendChild(li); inp.value = ""; nxChanged(); inp.focus();
  }
  if (NX && nxBox) {
    nxInit(); nxWrite();
    $(".next-add button", nxBox).addEventListener("click", nxAdd);
    $(".next-new", nxBox).addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); nxAdd(); } });
  } else { NX = null; }

  // ---------- DOM <-> state ----------
  function readQ(el) {
    var q = Q[el.dataset.q], qt = q.qt, v;
    switch (qt) {
      case "choice": case "pick": case "yesno": case "scale":
        var c = $("input:checked", el); v = c ? c.value : undefined; break;
      case "multi":
        v = $$("input:checked", el).map(function (i) { return i.value; }); break;
      case "todo":
        v = $$("input:checked", el).map(function (i) { return q.items[+i.value]; }); break;
      case "text": v = $("textarea", el).value; break;
      case "line": case "number": case "date": v = $("input", el).value; break;
      case "rank": v = $$(".rank li", el).map(function (li) { return li.dataset.val; }); break;
      case "approve":
        v = {};
        $$(".ap", el).forEach(function (row) {
          var s = $("input:checked", row), n = $(".note", row).value.trim();
          if (s || n) v[row.dataset.item] = { s: s ? s.value : "", n: n };
        });
        break;
      case "matrix":
        v = {};
        $$("tr[data-row]", el).forEach(function (tr) { var c = $("input:checked", tr); if (c) v[tr.dataset.row] = c.value; });
        break;
    }
    return v;
  }
  function writeQ(el) {
    var q = Q[el.dataset.q], v = S.a[q.id], ot = $(".other-txt", el);
    if (ot) ot.value = S.o[q.id] || "";
    switch (q.qt) {
      case "choice": case "pick": case "yesno": case "scale":
        $$("input:not(.other-txt)", el).forEach(function (i) { i.checked = v !== undefined && i.value === String(v); }); break;
      case "multi":
        $$("input:not(.other-txt)", el).forEach(function (i) { i.checked = (v || []).indexOf(i.value) >= 0; }); break;
      case "todo":
        $$("input", el).forEach(function (i) { i.checked = (v || []).indexOf(q.items[+i.value]) >= 0; }); break;
      case "text": $("textarea", el).value = v || ""; break;
      case "line": case "number": case "date": $("input", el).value = v || ""; break;
      case "rank":
        if (Array.isArray(v)) {
          var ol = $(".rank", el), lis = {};
          $$("li", ol).forEach(function (li) { lis[li.dataset.val] = li; });
          v.forEach(function (x) { if (lis[x]) ol.appendChild(lis[x]); });
        }
        rankNums(el); break;
      case "approve":
        $$(".ap", el).forEach(function (row) {
          var it = (v || {})[row.dataset.item] || {};
          $$("input[type=radio]", row).forEach(function (i) { i.checked = i.value === it.s; });
          $(".note", row).value = it.n || "";
        });
        break;
      case "matrix":
        $$("tr[data-row]", el).forEach(function (tr) {
          var c = (v || {})[tr.dataset.row];
          $$("input", tr).forEach(function (i) { i.checked = i.value === c; });
        });
        break;
    }
  }
  function otherTxt(q) { return A.otherTxt(q, S); }
  function eff(q) { return A.eff(q, S); }
  function answered(q) { return A.answered(q, S); }
  function rankNums(el) { $$(".rank li", el).forEach(function (li, k) { $(".rk", li).textContent = k + 1 + "."; }); }

  function refresh() {
    var total = P.questions.length, done = 0, miss = 0;
    P.questions.forEach(function (q) {
      var el = document.getElementById("q-" + q.id), a = answered(q);
      if (a) done++; else if (q.req) miss++;
      if (!el) return;
      el.classList.toggle("answered", a);
      if (a) el.classList.remove("req-miss");
      el.classList.toggle("is-reused", !!S.r[q.id]);
      var b = $(".badge.reused", el); if (b) b.hidden = !S.r[q.id];
    });
    $("#progBar").style.width = total ? (100 * done / total) + "%" : "100%";
    $("#progTxt").textContent = total ? t("progress", { a: done, t: total }) : "";
    $("#reqTxt").textContent = miss ? "· " + t("reqMissing", { n: miss }) : "";
    $("#reusedBanner").hidden = !Object.keys(S.r).length;
    if (typeof tocBadges === "function") tocBadges();
    $$(".cards[data-pick]").forEach(function (cs) {
      var v = S.a[cs.dataset.pick];
      $$(".card", cs).forEach(function (c) {
        var on = c.dataset.val === v;
        c.classList.toggle("sel", on);
        var btn = $(".pick-btn", c); if (btn) btn.textContent = t(on ? "chosen" : "choose");
      });
    });
    $$(".sec-comment").forEach(function (d) { d.classList.toggle("filled", !!(S.c[d.dataset.c] || "").trim()); });
  }

  function onChange(e) {
    if (NX && e.target.closest("#next")) { if (!e.target.classList.contains("next-new")) nxChanged(); return; }
    var qe = e.target.closest(".q");
    if (qe) {
      var id = qe.dataset.q;
      if (e.target.classList.contains("other-txt")) {
        S.o[id] = e.target.value;
        var box = e.target.parentNode.querySelector("input:not(.other-txt)");
        if (box && e.target.value.trim()) box.checked = true;
      }
      else if (e.type === "change" && e.target.value === OTHER && e.target.checked) {
        var tx = e.target.parentNode.querySelector(".other-txt"); if (tx && !tx.value) tx.focus();
      }
      var v = readQ(qe);
      S.a[id] = v; delete S.r[id];
      save(); refresh(); return;
    }
    var ce = e.target.closest(".sec-comment");
    if (ce) { S.c[ce.dataset.c] = e.target.value; save(); refresh(); }
  }

  // ---------- init DOM ----------
  $$(".q").forEach(writeQ);
  $$(".sec-comment").forEach(function (d) {
    var v = S.c[d.dataset.c]; if (v) { $("textarea", d).value = v; d.open = true; }
  });
  var main = $("#plan");
  main.addEventListener("input", onChange);
  main.addEventListener("change", onChange);

  // rank: buttons + drag & drop
  function rankChanged(el) { rankNums(el); S.a[el.dataset.q] = readQ(el); delete S.r[el.dataset.q]; save(); refresh(); }
  main.addEventListener("click", function (e) {
    var nb = e.target.closest(".next-list button");
    if (nb) {
      var nli = nb.closest("li"), nol = nli.parentNode;
      if (nb.classList.contains("del")) { nli.remove(); nxChanged(); return; }
      if (nb.classList.contains("up") && nli.previousElementSibling) nol.insertBefore(nli, nli.previousElementSibling);
      if (nb.classList.contains("down") && nli.nextElementSibling) nol.insertBefore(nli.nextElementSibling, nli);
      nxChanged(); nb.focus(); return;
    }
    var nl = e.target.closest(".next-list .lbl");
    if (nl && !e.target.closest("a")) { var cb = $("input", nl.parentNode); cb.checked = !cb.checked; nxChanged(); return; }
    var b = e.target.closest(".rank button");
    if (b) {
      var li = b.closest("li"), ol = li.parentNode;
      if (b.classList.contains("up") && li.previousElementSibling) ol.insertBefore(li, li.previousElementSibling);
      if (b.classList.contains("down") && li.nextElementSibling) ol.insertBefore(li.nextElementSibling, li);
      rankChanged(b.closest(".q")); b.focus(); return;
    }
    var card = e.target.closest(".cards[data-pick] .card");
    if (card && !e.target.closest("a")) {
      var qid = card.parentNode.dataset.pick, qe = document.getElementById("q-" + qid);
      if (!qe) return;
      $$("input", qe).forEach(function (i) { i.checked = i.value === card.dataset.val; });
      S.a[qid] = card.dataset.val; delete S.r[qid]; save(); refresh(); return;
    }
    var tab = e.target.closest(".tabbar button");
    if (tab) {
      var box = tab.closest(".tabs"), k = +tab.dataset.tab;
      $$(".tabbar button", box).forEach(function (x, j) { x.setAttribute("aria-selected", j === k); });
      $$(":scope > .pane", box).forEach(function (p, j) { p.hidden = j !== k; });
    }
  });
  var dragged = null;
  main.addEventListener("dragstart", function (e) {
    var li = e.target.closest && e.target.closest(".rank li"); if (!li) return;
    dragged = li; li.classList.add("drag"); e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", li.dataset.val); } catch (x) {}
  });
  main.addEventListener("dragover", function (e) {
    var li = e.target.closest && e.target.closest(".rank li");
    if (!dragged || !li || li.parentNode !== dragged.parentNode) return;
    e.preventDefault();
    $$(".over", li.parentNode).forEach(function (x) { x.classList.remove("over"); });
    if (li !== dragged) li.classList.add("over");
  });
  main.addEventListener("drop", function (e) {
    var li = e.target.closest && e.target.closest(".rank li");
    if (!dragged || !li || li.parentNode !== dragged.parentNode) return;
    e.preventDefault();
    var ol = li.parentNode, items = $$("li", ol);
    if (items.indexOf(dragged) < items.indexOf(li)) ol.insertBefore(dragged, li.nextSibling); else ol.insertBefore(dragged, li);
    if (ol.classList.contains("next-list")) nxChanged(); else rankChanged(li.closest(".q"));
  });
  main.addEventListener("dragend", function () {
    if (dragged) dragged.classList.remove("drag");
    $$(".rank .over").forEach(function (x) { x.classList.remove("over"); });
    dragged = null;
  });

  // ---------- answer generation ----------
  function short(s, n) { return A.short(s, n); }
  function build(ctx) { return A.build(NX ? P : Object.assign({}, P, { next: null }), S, ctx, t); }
  function toast(msg) {
    var el = $("#toast"); el.textContent = msg; el.classList.add("on");
    clearTimeout(toast.h); toast.h = setTimeout(function () { el.classList.remove("on"); }, 3200);
  }
  function showText(txt, msg) {
    var d = $("#outDlg"); $("#outMsg").textContent = msg; $("#outTxt").value = txt;
    if (d.showModal) d.showModal(); else d.setAttribute("open", "");
    $("#outTxt").focus(); $("#outTxt").select();
  }
  function fallbackCopy(txt) {
    var ta = document.createElement("textarea");
    ta.value = txt; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    var ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
    document.body.removeChild(ta); return ok;
  }
  // mode: false = answer, true = answer + context, "delta" = only what changed since the last sent answer
  function generate(ctx) {
    var cur = build(false).split("\n").slice(1), txt;
    if (ctx === "delta") {
      if (!Array.isArray(S.sent)) return generate(false);
      var d = A.delta(S.sent, cur);
      if (!d.changed) { toast(t("deltaNone")); return; }
      txt = "2CPC " + P.id + " v" + P.v + " Δ\n" + d.lines.join("\n");
    }
    var missing = ctx === "delta" ? [] : P.questions.filter(function (q) { return q.req && !answered(q); });
    if (missing.length) {
      missing.forEach(function (q) { var el = document.getElementById("q-" + q.id); if (el) el.classList.add("req-miss"); });
      var list = missing.map(function (q) { return "• " + short(q.label || q.id, 60); }).join("\n");
      if (!confirm(t("reqConfirm", { list: list }))) {
        var first = document.getElementById("q-" + missing[0].id); if (first) first.scrollIntoView({ block: "center" });
        return;
      }
    }
    if (ctx !== "delta") txt = build(ctx);
    S.sent = cur; save(); deltaBtns();
    var done = function () { toast(t("copied")); };
    var fail = function () { if (fallbackCopy(txt)) done(); else showText(txt, t("copyFail")); };
    if (navigator.clipboard && window.isSecureContext !== false) navigator.clipboard.writeText(txt).then(done, fail);
    else fail();
  }
  function deltaBtns() { $$("#btnDelta, .end-actions [data-act=delta]").forEach(function (b) { b.hidden = !Array.isArray(S.sent); }); }
  $("#btnAnswer").addEventListener("click", function () { generate(false); });
  $("#btnContext").addEventListener("click", function () { generate(true); });
  $("#btnDelta").addEventListener("click", function () { generate("delta"); });
  $$(".end-actions [data-act]").forEach(function (b) {
    b.addEventListener("click", function () { generate(b.dataset.act === "delta" ? "delta" : b.dataset.act === "context"); });
  });
  deltaBtns();

  // ---------- changes since v(N-1) (A3) & previous answers (A4) ----------
  var chgBar = $("#chgBar"), chgOn = false;
  function chgLabels() {
    if (chgBar) {
      $(".chg-txt", chgBar).textContent = t("chgSummary", { v: chgBar.dataset.pv, c: chgBar.dataset.c, n: chgBar.dataset.n });
      $("#chgOnly").textContent = t(chgOn ? "chgAll" : "chgOnly");
    }
    $$(".prev-ans b").forEach(function (b) { b.textContent = t("prevAns", { v: prevV() }); });
  }
  function chgFilter() {
    var st = null, secs = {};
    $$("#plan > *").forEach(function (el) {
      if (el.id === "next" || el.id === "chgBar" || el.id === "reusedBanner" || el.classList.contains("end-actions")) return;
      if (el.dataset.sec) { st = el.dataset.sec; secs[el.id] = st; }
      el.classList.toggle("chg-hide", chgOn && st === "same");
    });
    st = null;
    $$(".toc li").forEach(function (li) {
      var a = $("a", li), id = a && a.getAttribute("href").slice(1);
      if (id in secs) st = secs[id]; else if (id === "next") st = null;
      li.classList.toggle("chg-hide", chgOn && st === "same");
    });
  }
  if (chgBar) $("#chgOnly").addEventListener("click", function () { chgOn = !chgOn; chgFilter(); chgLabels(); });

  var prevS = P.prevKey && P.prevQ && Object.keys(P.prevQ).length ? load(P.prevKey) : null;
  if (prevS && prevS.a) {
    prevS.o = prevS.o || {}; prevS.c = prevS.c || {};
    Object.keys(P.prevQ).forEach(function (id) {
      var pq = P.prevQ[id], el = document.getElementById("q-" + id), lb = el && $(".q-label", el);
      if (!lb || !A.answered(pq, prevS)) return;
      var txt = A.lines(pq, A.eff(pq, prevS), true, prevS, t).map(function (l) {
        return l.indexOf(id + ".") === 0 ? l.slice(id.length + 1).replace("=", " ") : l.slice(l.indexOf("=") + 1);
      }).join(" · ");
      var d = document.createElement("div");
      d.className = "prev-ans"; d.innerHTML = "<b></b> ";
      d.appendChild(document.createTextNode(txt));
      lb.parentNode.insertBefore(d, lb.nextSibling);
    });
  }
  chgLabels();

  // ---------- copyable code blocks (!code, !cmd): "copied" state is remembered (tutorial progress) ----------
  S.cp = S.cp || {};
  function copyText(txt, ok) {
    var fb = function () { if (fallbackCopy(txt)) ok(); else showText(txt, t("copyFail")); };
    if (navigator.clipboard && window.isSecureContext !== false) navigator.clipboard.writeText(txt).then(ok, fb);
    else fb();
  }
  $$("[data-copy]").forEach(function (box) {
    var btn = $(".copy", box);
    if (S.cp[box.dataset.ck]) box.classList.add("copied");
    if (btn) btn.addEventListener("click", function () {
      copyText(box.dataset.copy, function () {
        box.classList.add("copied"); btn.textContent = t("copyDone");
        S.cp[box.dataset.ck] = 1; save();
        setTimeout(function () { btn.textContent = t("copyBtn"); }, 1600);
      });
    });
  });

  // ---------- !compare slider ----------
  $$(".cmp-box input[type=range]").forEach(function (r) {
    r.addEventListener("input", function () { r.parentNode.style.setProperty("--pos", r.value + "%"); });
  });

  // ---------- sections: search, "unanswered only" (D3), toc badges (D4) ----------
  var SPECIAL = { next: 1, chgBar: 1, reusedBanner: 1 }, GR = null;
  // #plan children grouped by level-1/2 heading: [{id, els, qs: [question ids]}]
  function groups() {
    if (GR) return GR;
    GR = []; var cur = { id: null, els: [], qs: [] }; GR.push(cur);
    $$("#plan > *").forEach(function (el) {
      if (SPECIAL[el.id] || el.classList.contains("end-actions")) return;
      if (el.tagName === "H2" || el.tagName === "H3") { cur = { id: el.id, els: [], qs: [] }; GR.push(cur); }
      cur.els.push(el);
      $$(".q[data-q]", el).forEach(function (q) { cur.qs.push(q.dataset.q); });
      if (el.dataset.q) cur.qs.push(el.dataset.q);
    });
    return GR;
  }
  function fold(s) { return String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }
  function unmark() {
    $$("mark.hit").forEach(function (m) { var p = m.parentNode; p.replaceChild(document.createTextNode(m.textContent), m); p.normalize(); });
  }
  function markIn(el, q) {
    var w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.parentNode.closest("script,style,textarea,mark,.ap-btns") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    }), nodes = [], n;
    while ((n = w.nextNode())) nodes.push(n);
    nodes.forEach(function (tn) {
      var txt = tn.nodeValue, low = txt.toLowerCase(), i = low.indexOf(q);
      if (i < 0) return;
      var frag = document.createDocumentFragment(), last = 0;
      while (i >= 0) {
        frag.appendChild(document.createTextNode(txt.slice(last, i)));
        var m = document.createElement("mark"); m.className = "hit"; m.textContent = txt.slice(i, i + q.length);
        frag.appendChild(m); last = i + q.length; i = low.indexOf(q, last);
      }
      frag.appendChild(document.createTextNode(txt.slice(last)));
      tn.parentNode.replaceChild(frag, tn);
    });
  }
  var srch = $("#search"), onlyOpen = $("#onlyOpen");
  function applyFilters() {
    var q = srch ? srch.value.trim() : "", fq = fold(q), open = onlyOpen && onlyOpen.checked, vis = {};
    unmark();
    groups().forEach(function (g) {
      var show = true;
      if (fq) show = fold(g.els.map(function (e) { return e.textContent; }).join(" ")).indexOf(fq) >= 0;
      var todo = g.qs.filter(function (id) { return !answered(Q[id]); });
      if (open && !todo.length) show = false;
      g.els.forEach(function (e) { e.classList.toggle("f-hide", !show); });
      g.els.forEach(function (e) {
        $$(".q[data-q]", e).concat(e.dataset.q ? [e] : []).forEach(function (qe) {
          qe.classList.toggle("q-hide", !!open && show && answered(Q[qe.dataset.q]));
        });
      });
      if (show && q) g.els.forEach(function (e) { markIn(e, q.toLowerCase()); });
      if (g.id) vis[g.id] = show;
    });
    var st = true;
    $$(".toc li").forEach(function (li) {
      var a = $("a", li), id = a && a.getAttribute("href").slice(1);
      if (id in vis) st = vis[id]; else if (id === "next") st = true;
      li.classList.toggle("f-hide", !st);
    });
    var first = q && $("mark.hit");
    if (first) first.scrollIntoView({ block: "center" });
  }
  var srchT;
  if (srch) srch.addEventListener("input", function () { clearTimeout(srchT); srchT = setTimeout(applyFilters, 150); });
  if (srch) srch.addEventListener("keydown", function (e) { if (e.key === "Escape") { srch.value = ""; applyFilters(); } });
  if (onlyOpen) onlyOpen.addEventListener("change", applyFilters);
  document.addEventListener("keydown", function (e) {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "F" || e.key === "f") && srch) { e.preventDefault(); srch.focus(); srch.select(); }
  });
  function tocBadges() {
    var by = {};
    groups().forEach(function (g) {
      if (!g.id) return;
      var left = 0, req = false;
      g.qs.forEach(function (id) { if (!answered(Q[id])) { left++; if (Q[id].req) req = true; } });
      by[g.id] = { n: left, req: req, any: g.qs.length > 0 };
    });
    $$(".toc li").forEach(function (li) {
      var a = $("a", li), id = a && a.getAttribute("href").slice(1), b = by[id];
      if (!b || !b.any) return;
      var pill = $(".toc-n", li);
      if (!pill) { pill = document.createElement("span"); pill.className = "toc-n"; a.appendChild(pill); }
      pill.textContent = b.n ? String(b.n) : "✓";
      pill.classList.toggle("ok", !b.n);
      pill.classList.toggle("req", b.req);
    });
  }

  // ---------- export / import / reset / lang ----------
  function closeMenu() { var m = $(".more"); if (m) m.open = false; }
  $("#btnExport").addEventListener("click", function () {
    var blob = new Blob([JSON.stringify({ plan: P.id, v: P.v, key: P.key, state: S }, null, 2)], { type: "application/json" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "2cpc-" + P.id + "-v" + P.v + ".json";
    document.body.appendChild(a); a.click(); a.remove(); closeMenu();
  });
  $("#fileImport").addEventListener("change", function (e) {
    var f = e.target.files[0]; if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      try {
        var o = JSON.parse(rd.result), st = o.state || o;
        if (!st || typeof st.a !== "object") throw 0;
        S = { a: st.a || {}, c: st.c || {}, o: st.o || {}, r: {}, n: st.n };
        save(); location.reload();
      } catch (x) { alert(t("importFail")); }
    };
    rd.readAsText(f); closeMenu();
  });
  $("#btnReset").addEventListener("click", function () {
    if (!confirm(t("resetConfirm"))) return;
    try { localStorage.removeItem(P.key); } catch (e) {}
    location.reload();
  });
  $$(".langs button").forEach(function (b) {
    b.addEventListener("click", function () {
      lang = b.dataset.lang; try { localStorage.setItem("2cpc:lang", lang); } catch (e) {}
      applyLang(); closeMenu();
    });
  });
  document.addEventListener("click", function (e) { var m = $(".more"); if (m && m.open && !m.contains(e.target)) m.open = false; });

  // ---------- toc highlight ----------
  if ("IntersectionObserver" in window) {
    var links = {}; $$(".toc a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (ents) {
      ents.forEach(function (en) {
        if (en.isIntersecting && links[en.target.id]) {
          $$(".toc a.on").forEach(function (x) { x.classList.remove("on"); });
          links[en.target.id].classList.add("on");
        }
      });
    }, { rootMargin: "-100px 0px -70% 0px" });
    Object.keys(links).forEach(function (id) { var h = document.getElementById(id); if (h) io.observe(h); });
  }

  // ---------- broken web images ----------
  $$("figure.img img").forEach(function (im) {
    function bad() {
      var d = document.createElement("div"); d.className = "missing";
      d.textContent = "⚠ " + im.getAttribute("src");
      var a = im.closest("a"); (a || im).replaceWith(d);
    }
    if (im.complete && im.naturalWidth === 0 && im.src) bad(); else im.addEventListener("error", bad);
  });

  // ---------- mermaid ----------
  if ($(".mermaid")) {
    window.addEventListener("load", function () {
      if (window.mermaid) {
        try {
          var dark = window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches;
          window.mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "default", securityLevel: "strict" });
          window.mermaid.run({ querySelector: ".mermaid" });
        } catch (e) { $$(".mm-off").forEach(function (x) { x.hidden = false; }); }
      } else {
        $$(".mm-off").forEach(function (x) { x.hidden = false; });
      }
    });
  }

  applyLang();
})();
