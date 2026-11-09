// Answer text generation — pure functions, no DOM (shared by app.js and tests/answers.test.js).
// P = window.PLAN, S = stored state {a, o, c, n}, t = i18n function (key, vars) -> string.
(function (root) {
  "use strict";
  var OTHER = "__other";

  function clean(s) { return String(s).replace(/[*`_\[\]]/g, "").replace(/\s+/g, " ").trim(); }
  function short(s, n) { s = clean(s).replace(/\s*[?:]+$/, ""); return s.length > n ? s.slice(0, n - 1).trim() + "…" : s; }
  function lbl(q, k) { return (q.labels && q.labels[k]) || k; }
  function optOut(q, k, ctx) {
    if (!q.keyed) return clean(k);
    return ctx && lbl(q, k) !== k ? k + "(" + short(lbl(q, k), 25) + ")" : k;
  }
  function joinSafe(list, sep, alt) {
    return list.join(list.some(function (x) { return x.charAt(0) !== '"' && x.indexOf(sep) >= 0; }) ? alt : sep);
  }
  function otherTxt(q, S) { return String((S.o || {})[q.id] || "").trim(); }
  // value without an empty "other" entry
  function eff(q, S) {
    var v = S.a[q.id];
    if (!q.other) return v;
    if (v === OTHER) return otherTxt(q, S) ? v : undefined;
    if (Array.isArray(v) && !otherTxt(q, S)) return v.filter(function (x) { return x !== OTHER; });
    return v;
  }
  function answered(q, S) {
    var v = eff(q, S);
    if (v === undefined || v === null || v === "") return false;
    if (Array.isArray(v)) return v.length > 0;
    if (typeof v === "object") return Object.keys(v).length > 0;
    return String(v).trim() !== "";
  }
  // -> array of "key=value" lines for one question
  function lines(q, v, ctx, S, t) {
    var base = q.id + (ctx && q.label ? "(" + short(q.label, 30) + ")" : ""), val;
    switch (q.qt) {
      case "approve":
        return (q.opts || []).filter(function (o) { return v[o]; }).map(function (o) {
          var it = v[o], sym = { y: "✓", n: "✗", "?": "?" }[it.s] || "";
          var key = q.id + "." + (q.keyed ? o : short(o, 40)) + (ctx && q.keyed && lbl(q, o) !== o ? "(" + short(lbl(q, o), 25) + ")" : "");
          return key + "=" + [sym, it.n ? JSON.stringify(it.n) : ""].filter(Boolean).join(" ");
        });
      case "yesno": val = t(v); break;
      case "scale": val = v + "/" + q.max; break;
      case "choice": case "pick": val = v === OTHER ? JSON.stringify(otherTxt(q, S)) : optOut(q, v, ctx); break;
      case "multi":
        val = joinSafe(v.map(function (k) { return k === OTHER ? JSON.stringify(otherTxt(q, S)) : optOut(q, k, ctx); }), ",", " ; "); break;
      case "rank": val = joinSafe(v.map(function (k) { return optOut(q, k, ctx); }), ">", " ; "); break;
      case "text": case "line": val = JSON.stringify(v.trim()); break;
      case "todo": val = v.length + "/" + q.items.length + (v.length ? " " + v.map(function (x) { return "✓" + clean(x); }).join(" ") : ""); break;
      case "matrix":
        val = (q.rows || []).filter(function (r) { return v[r]; }).map(function (r) { return clean(r) + ":" + v[r]; }).join(", "); break;
      default: val = String(v);
    }
    return [base + "=" + val];
  }
  // next=k1>k2>"custom" (ticked steps, in order) · next.pause=oui · next.note="…"
  function nextLines(P, S, ctx, t) {
    var NX = P.next, n = S.n || {}, out = [];
    var on = (n.items || []).filter(function (it) { return it.on; });
    if (on.length) {
      out.push("next=" + on.map(function (it) {
        if (it.c) return JSON.stringify(it.c);
        var L = (NX.labels && NX.labels[it.k]) || it.k;
        return ctx && L !== it.k ? it.k + "(" + short(L, 30) + ")" : it.k;
      }).join(">"));
      if (n.pause) out.push("next.pause=" + t("yes"));
    }
    var note = String(n.note || "").trim();
    if (note) out.push("next.note=" + JSON.stringify(note));
    return out;
  }
  function build(P, S, ctx, t) {
    var L = [];
    if (ctx) {
      L.push(t("ctxHead", { t: P.title, v: P.v, d: P.date }));
      if (P.intro) L.push(t("ctxIntro") + " : " + clean(P.intro));
      L.push(t("ctxProject") + " : " + P.project);
      L.push(t("ctxPlan") + " : " + P.planPath);
      L.push(t("ctxTool") + " : " + t("ctxToolLine", { tool: P.tool, n: P.v + 1, id: P.id }));
      L.push("---");
    } else {
      L.push("2CPC " + P.id + " v" + P.v);
    }
    P.questions.forEach(function (q) {
      if (answered(q, S)) L.push.apply(L, lines(q, eff(q, S), ctx, S, t));
    });
    (P.sections || []).forEach(function (s) {
      var c = ((S.c || {})[s.id] || "").trim();
      if (c) L.push("#" + short(s.text, 30) + "=" + JSON.stringify(c));
    });
    if (P.next) L.push.apply(L, nextLines(P, S, ctx, t));
    return L.join("\n");
  }

  // "What's new" since the last sent answer: changed/added lines, `key=` for cleared ones, next.* lines always kept.
  // prev/cur: compact answer lines without the header. -> {lines: [...], changed: n}
  function keyOf(l) { var i = l.indexOf("="); return i < 0 ? l : l.slice(0, i); }
  function isNext(k) { return k === "next" || k.indexOf("next.") === 0; }
  function delta(prev, cur) {
    var pm = {}, cm = {}, out = [], n = 0;
    prev.forEach(function (l) { pm[keyOf(l)] = l; });
    cur.forEach(function (l) { cm[keyOf(l)] = l; });
    cur.forEach(function (l) {
      var k = keyOf(l), ch = pm[k] !== l;
      if (ch) n++;
      if (ch || isNext(k)) out.push(l);
    });
    prev.forEach(function (l) { var k = keyOf(l); if (!(k in cm)) { n++; if (!isNext(k)) out.push(k + "="); } });
    return { lines: out, changed: n };
  }

  var api = { OTHER: OTHER, clean: clean, short: short, otherTxt: otherTxt, eff: eff, answered: answered,
              lines: lines, nextLines: nextLines, build: build, delta: delta };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CPCAnswers = api;
})(this);
