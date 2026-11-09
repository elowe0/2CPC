// Tests of the answer text generation (cpc/template/answers.js). Run: node --test tests/answers.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const A = require(path.join(__dirname, "..", "cpc", "template", "answers.js"));

const STR = {
  yes: "oui", no: "non",
  ctxHead: "[2CPC] Réponses au plan interactif « {t} » (v{v}, {d})",
  ctxIntro: "Intro", ctxProject: "Projet", ctxPlan: "Plan", ctxTool: "Outil",
  ctxToolLine: "python \"{tool}\" (skill 2cpc ; v{n} : new --id {id})",
};
const t = (k, vars) => {
  let s = STR[k] || k;
  if (vars) for (const v of Object.keys(vars)) s = s.split("{" + v + "}").join(vars[v]);
  return s;
};
const plan = (questions, extra = {}) => Object.assign({
  id: "demo", v: 2, title: "Demo", intro: "Une **intro**.", date: "2026-11-09",
  project: "C:/p", planPath: "C:/p/.2cpc/demo/v2/plan.txt", tool: "C:/t/cpc.py",
  questions, sections: [], next: null,
}, extra);
const st = (a, extra = {}) => Object.assign({ a, o: {}, c: {}, r: {} }, extra);
const body = (P, S, ctx = false) => A.build(P, S, ctx, t).split("\n").slice(ctx ? 6 : 1);

const KEYED = { opts: ["pg", "lite"], labels: { pg: "PostgreSQL (prod)", lite: "SQLite" }, keyed: true };

test("header line", () => {
  assert.equal(A.build(plan([]), st({}), false, t), "2CPC demo v2");
});

test("choice: keyed, unkeyed, other, empty other ignored", () => {
  const q1 = Object.assign({ id: "db", qt: "choice", label: "DB ?", other: true }, KEYED);
  const q2 = { id: "c2", qt: "choice", label: "X", opts: ["A **b**", "C"] };
  assert.deepEqual(body(plan([q1, q2]), st({ db: "pg", c2: "A **b**" })), ["db=pg", "c2=A b"]);
  assert.deepEqual(body(plan([q1]), st({ db: A.OTHER }, { o: { db: "Mongo" } })), ['db="Mongo"']);
  assert.deepEqual(body(plan([q1]), st({ db: A.OTHER })), []);
});

test("multi and rank: separators, fallback when a label contains the separator", () => {
  const m = Object.assign({ id: "f", qt: "multi", label: "F", other: true }, KEYED);
  assert.deepEqual(body(plan([m]), st({ f: ["pg", A.OTHER] }, { o: { f: "a,b" } })), ['f=pg,"a,b"']);
  const m2 = { id: "g", qt: "multi", label: "G", opts: ["x, y", "z"] };
  assert.deepEqual(body(plan([m2]), st({ g: ["x, y", "z"] })), ["g=x, y ; z"]);
  const r = Object.assign({ id: "r", qt: "rank", label: "R" }, KEYED);
  assert.deepEqual(body(plan([r]), st({ r: ["lite", "pg"] })), ["r=lite>pg"]);
});

test("approve: one line per item, symbol + note, unanswered items omitted", () => {
  const q = { id: "s", qt: "approve", label: "S", opts: ["P1", "P2", "P3"], labels: { P1: "Un", P2: "Deux", P3: "Trois" }, keyed: true };
  const v = { P1: { s: "y" }, P2: { s: "n", n: "trop tôt" }, P3: { n: "à voir" } };
  assert.deepEqual(body(plan([q]), st({ s: v })), ["s.P1=✓", 's.P2=✗ "trop tôt"', 's.P3="à voir"']);
});

test("yesno, scale, number, text, line, matrix, todo", () => {
  const qs = [
    { id: "go", qt: "yesno", label: "Go" },
    { id: "p", qt: "scale", label: "P", min: 1, max: 5 },
    { id: "n", qt: "number", label: "N" },
    { id: "tx", qt: "text", label: "T" },
    { id: "ln", qt: "line", label: "L" },
    { id: "mx", qt: "matrix", label: "M", rows: ["A", "B"], cols: ["x", "y"] },
    { id: "todo", qt: "todo", label: "", items: ["Faire **A**", "B", "C"] },
  ];
  const S = st({ go: "yes", p: "4", n: "12", tx: '  dit "ok"\nfin ', ln: "", mx: { B: "y" }, todo: ["Faire **A**"] });
  assert.deepEqual(body(plan(qs), S), ["go=oui", "p=4/5", "n=12", 'tx="dit \\"ok\\"\\nfin"', "mx=B:y", "todo=1/3 ✓Faire A"]);
});

test("section comments", () => {
  const P = plan([], { sections: [{ id: "s1", text: "Contexte général du projet et contraintes" }, { id: "s2", text: "Vide" }] });
  assert.deepEqual(body(P, st({}, { c: { s1: " ok " } })), ['#Contexte général du projet et…="ok"']);
});

test("next: ticked steps in order, custom step, pause and note", () => {
  const P = plan([], { next: { opts: ["revise", "exec"], labels: { revise: "Intégrer", exec: "Implémenter" }, keyed: true } });
  const S = st({}, { n: { items: [{ k: "exec", on: true }, { k: "revise", on: false }, { c: "Ma > étape", on: true }], pause: true, note: "vite" } });
  assert.deepEqual(body(P, S), ['next=exec>"Ma > étape"', "next.pause=oui", 'next.note="vite"']);
  assert.deepEqual(body(P, st({}, { n: { items: [], pause: true } })), [], "pause alone is not sent");
  assert.deepEqual(body(P, st({})), [], "no state.n");
});

test("context mode: header and labels", () => {
  const q = Object.assign({ id: "db", qt: "choice", label: "Quelle base de données utiliser ?" }, KEYED);
  const P = plan([q], { next: { opts: ["exec"], labels: { exec: "Implémenter" }, keyed: true } });
  const out = A.build(P, st({ db: "pg" }, { n: { items: [{ k: "exec", on: true }] } }), true, t).split("\n");
  assert.equal(out[0], "[2CPC] Réponses au plan interactif « Demo » (v2, 2026-11-09)");
  assert.equal(out[1], "Intro : Une intro.");
  assert.equal(out[4], 'Outil : python "C:/t/cpc.py" (skill 2cpc ; v3 : new --id demo)');
  assert.equal(out[5], "---");
  assert.deepEqual(out.slice(6), ["db(Quelle base de données utilis…)=pg(PostgreSQL (prod))", "next=exec(Implémenter)"]);
});

test("delta: changed, added, cleared lines; next always kept", () => {
  const prev = ["db=pg", "f=a,b", "s.A1=✓", 'tx="x"', "next=revise"];
  const cur = ["db=pg", "f=a", "s.A1=✓", "s.A2=✗", "next=revise"];
  assert.deepEqual(A.delta(prev, cur), { lines: ["f=a", "s.A2=✗", "next=revise", "tx="], changed: 3 });
  assert.deepEqual(A.delta(prev, prev), { lines: ["next=revise"], changed: 0 });
  assert.equal(A.delta(["next=a"], ["next=b"]).changed, 1);
});

test("short / clean", () => {
  assert.equal(A.short("**Gras** et `code` ?", 30), "Gras et code");
  assert.equal(A.short("abcdefghij", 5), "abcd…");
});
