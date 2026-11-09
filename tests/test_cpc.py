import io
import os
import re
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cpc as _pkg  # noqa: E402,F401
from cpc.parser import parse  # noqa: E402
from cpc.markdown import inline  # noqa: E402
from cpc import charts, draw  # noqa: E402
from cpc.render import Ctx, block  # noqa: E402

import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("cpc_cli", ROOT / "cpc.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

SAMPLE = """title: Demo
lang: en
intro: Short intro.
# Context
Hello **world**.
- a
- b
> note: careful
!chart bar | Cost | A=1, B=2.5
!cards
X | desc | + good ; - bad
Y | other
!end
?pick opt! | Which?
?choice db | DB? | PG* ; SQLite
?multi f | Features | E ; W
?scale p | Prio | 1-3
?matrix m | Fit | R1 ; R2 | C1 ; C2
!cols
left
!col
right
!end
!todo t1 ; t2
"""


class ParserTest(unittest.TestCase):
    def test_meta_and_blocks(self):
        p = parse(SAMPLE)
        self.assertEqual(p.meta["title"], "Demo")
        self.assertEqual(p.meta["lang"], "en")
        types = [b["t"] for b in p.blocks]
        self.assertEqual(types[:6], ["h", "p", "ul", "callout", "chart", "cards"])
        self.assertIn("cols", types)
        self.assertEqual(p.warnings, [])

    def test_table_rows_any_line_endings(self):
        # \r\r\n = CRLF text re-written in text mode on Windows
        for eol in ("\n", "\r\n", "\r", "\r\r\n"):
            p = parse(eol.join(["!table | A | B", "| a | b", "| c | d", "after"]))
            self.assertEqual(p.blocks[0]["rows"], [["a", "b"], ["c", "d"]], repr(eol))
            self.assertEqual(p.blocks[1], {"t": "p", "text": "after"})

    def test_questions(self):
        p = parse(SAMPLE)
        q = {x["id"]: x for x in p.questions}
        self.assertEqual(list(q), ["opt", "db", "f", "p", "m", "todo"])
        self.assertTrue(q["opt"]["req"])
        self.assertEqual(q["opt"]["opts"], ["X", "Y"])
        self.assertEqual(q["db"]["rec"], ["PG"])
        self.assertEqual((q["p"]["min"], q["p"]["max"]), (1, 3))
        self.assertEqual(q["m"]["cols"], ["C1", "C2"])
        self.assertEqual(q["todo"]["items"], ["t1", "t2"])

    def test_warnings(self):
        p = parse("!bogus x\n?choice a | q | x\n?choice a | q | y\n!cols\nx")
        w = " ".join(p.warnings)
        self.assertIn("unknown directive", w)
        self.assertIn("duplicate id", w)
        self.assertIn("unclosed", w)
        self.assertEqual([q["id"] for q in p.questions], ["a", "a2"])

    def test_inline_escapes(self):
        self.assertEqual(inline("<b> **x** `<i>`"), "&lt;b&gt; <strong>x</strong> <code>&lt;i&gt;</code>")
        self.assertIn('href="#"', inline("[x](javascript:alert(1))"))

    def test_charts(self):
        for kind in ("bar", "hbar", "line", "pie", "donut"):
            html = charts.render({"kind": kind, "title": "T", "data": [("A", 1), ("B", 3)]})
            self.assertIn("<svg", html)


class FeedbackTest(unittest.TestCase):
    def test_doc_example_is_clean(self):
        doc = (ROOT / "docs" / "DSL.md").read_text(encoding="utf-8")
        ex = doc.split("## Example")[1].split("```")[1]
        p = parse(ex)
        self.assertEqual(p.warnings, [])
        self.assertEqual(len(p.questions), 6)

    def test_escapes(self):
        p = parse(r"?choice c | A \| B | x\;y ; z" "\n" r"!kpi K=a\;b" "\n!code\n" r"a \; b" "\n!end")
        q = p.questions[0]
        self.assertEqual(q["label"], "A | B")
        self.assertEqual(q["opts"], ["x;y", "z"])
        self.assertEqual(p.blocks[1]["items"], [("K", "a;b")])
        self.assertEqual(p.blocks[2]["text"], r"a \; b")
        self.assertEqual(p.warnings, [])

    def test_keys_and_details(self):
        p = parse("?approve a | Q | BLD-01=Citadelle (P1, Gong) :: long detail ; BLD-05=Scierie ; Plain")
        q = p.questions[0]
        self.assertEqual(q["opts"], ["BLD-01", "BLD-05", "Plain"])
        self.assertEqual(q["labels"]["BLD-01"], "Citadelle (P1, Gong)")
        self.assertEqual(q["details"], {"BLD-01": "long detail"})
        self.assertTrue(q["keyed"])

    def test_defaults_and_ranges(self):
        p = parse("?number n | Q | 4-16 | 10\n?number m | Q | 7\n?yesno y | Q | non\n"
                  "?scale s | Q | 1-5 | 3\n?line l | Q | x")
        q = {x["id"]: x for x in p.questions}
        self.assertEqual((q["n"]["min"], q["n"]["max"], q["n"]["def"]), (4, 16, "10"))
        self.assertEqual(q["m"]["def"], "7")
        self.assertEqual(q["y"]["def"], "no")
        self.assertEqual(q["s"]["def"], "3")
        self.assertEqual(q["l"]["def"], "x")
        self.assertEqual(p.warnings, [])

    def test_new_warnings(self):
        p = parse("?text t | Q | d | extra\n?rank r | Q | A* ; ; B\n?foo x | y\n?number n | Q | 1-5 | 9")
        w = " ".join(p.warnings)
        for frag in ("extra '|'", "'*' ignored", "empty item", "unknown question type", "out of range"):
            self.assertIn(frag, w)


class DrawTest(unittest.TestCase):
    SRC = ("!draw Plot\ngrid\ncircle 0,0 5.6 .empty .dash\nbox -3,-2 6,3.5 .blue Forge\n"
           "dot 0,4.6 .red PathEndSpot ; text 0,-4 back\narrow 3,-3 4,-1 3,1 .curve .both zone\n"
           "poly -4,-1 -3,-3 -3,1 .green\nline 0,0 1,1\n!end")

    def test_parse(self):
        p = parse(self.SRC)
        self.assertEqual(p.warnings, [])
        d = p.blocks[0]
        self.assertEqual((d["t"], d["caption"], d["grid"]), ("draw", "Plot", 1.0))
        cmds = [s["cmd"] for s in d["shapes"]]
        self.assertEqual(cmds, ["circle", "box", "dot", "text", "arrow", "poly", "line"])
        c = d["shapes"][0]
        self.assertEqual((c["r"], c["flags"], c["label"]), (5.6, ["dash", "empty"], ""))
        self.assertEqual(d["shapes"][1]["color"], "s1")
        self.assertEqual(d["shapes"][1]["label"], "Forge")
        self.assertEqual(d["shapes"][4]["flags"], ["both", "curve"])

    def test_render(self):
        d = parse(self.SRC).blocks[0]
        html = block(d, Ctx(".", ".", set()))
        self.assertIn('<figure class="draw"><svg viewBox=', html)
        for frag in ("<circle", "<rect", "<polygon", "<path", "PathEndSpot", "<figcaption>Plot"):
            self.assertIn(frag, html)
        self.assertEqual(html.count('class="hd"'), 2)    # .both -> 2 arrowheads

    def test_warnings(self):
        p = parse("!draw\nstar 1,1\nbox 1,1\ncircle 0,0\ntext 1,1\n!end\n!draw\n!end")
        w = " ".join(p.warnings)
        for frag in ("unknown shape 'star'", "box: needs 2", "radius", "empty label", "no shapes"):
            self.assertIn(frag, w)


class OtherOptionTest(unittest.TestCase):
    def test_default_on(self):
        p = parse("?choice c | Q | A ; B\n?multi m | Q | A ; B\n?rank r | Q | A ; B")
        q = {x["id"]: x for x in p.questions}
        self.assertTrue(q["c"]["other"] and q["m"]["other"])
        self.assertNotIn("other", q["r"])
        html = block(q["c"], Ctx(".", ".", set()))
        self.assertIn('value="__other"', html)
        self.assertIn('class="other-txt"', html)

    def test_header_off(self):
        p = parse("other: off\n?choice c | Q | A ; B")
        self.assertFalse(p.questions[0]["other"])
        self.assertNotIn("__other", block(p.questions[0], Ctx(".", ".", set())))


class CliBase(unittest.TestCase):
    """Temp project + isolated home; no tests here."""
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "a.png").write_bytes(b"\x89PNG fake")
        self.home = Path(tempfile.mkdtemp())  # registry + installed skill: never the real ~/.2cpc / ~/.claude
        self._env = {k: os.environ.get(k) for k in ("CPC_HOME", "CPC_SKILL_FILE")}
        os.environ["CPC_HOME"] = str(self.home / ".2cpc")
        os.environ["CPC_SKILL_FILE"] = str(self.home / "SKILL.md")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.home, ignore_errors=True)

    def run_cli(self, argv, stdin_text=None):
        f = None
        if stdin_text is not None:
            f = self.dir / "_in.txt"
            f.write_text(stdin_text, encoding="utf-8")
            argv = argv + ["--file", str(f)]
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--root", str(self.dir)] + argv)
        return buf.getvalue()

    def page_plan(self, pid, v=1):
        html = (self.dir / ".2cpc" / pid / f"v{v}" / "index.html").read_text(encoding="utf-8")
        return html, json.loads(html.split("window.PLAN=")[1].split(";window.I18N=")[0])


    def write(self, text):
        f = self.dir / "_w.txt"
        f.write_text(text, encoding="utf-8")
        return f


class CliTest(CliBase):
    def test_new_and_version(self):
        out = self.run_cli(["new", "--no-open"], SAMPLE + "!img a.png | pic\n")
        self.assertTrue(out.startswith("OK demo v1"), out)
        v1 = self.dir / ".2cpc" / "demo" / "v1"
        html = (v1 / "index.html").read_text(encoding="utf-8")
        self.assertIn("window.PLAN=", html)
        m = re.search(r'src="\.\./assets/([0-9a-f]{8}-a\.png)"', html)
        self.assertTrue(m, "shared asset url")
        self.assertTrue((v1.parent / "assets" / m.group(1)).is_file())
        self.assertFalse((v1 / "assets").exists())
        plan = json.loads(html.split("window.PLAN=")[1].split(";window.I18N=")[0])
        self.assertEqual(plan["intro"], "Short intro.")
        self.assertIsNone(plan["prevKey"])

        out = self.run_cli(["new", "--id", "demo", "--no-open"], SAMPLE + "?line extra | New\n")
        self.assertTrue(out.startswith("OK demo v2"), out)
        html2 = (self.dir / ".2cpc" / "demo" / "v2" / "index.html").read_text(encoding="utf-8")
        plan2 = json.loads(html2.split("window.PLAN=")[1].split(";window.I18N=")[0])
        self.assertEqual(plan2["prevKey"], plan["key"].replace(":v1", ":v1"))
        self.assertEqual(html2.count("badge new"), 1)
        self.assertIn('href="../v2/index.html"', (v1 / "index.html").read_text(encoding="utf-8"))

        self.assertIn("demo v2", self.run_cli(["list"]))
        self.assertTrue(self.run_cli(["path", "demo"]).strip().endswith("plan.txt"))

    def test_check_and_positional_file(self):
        f = self.dir / "p.dsl"
        f.write_text("title: Chk\n# S\n?choice a | Q | x ; y\n!img nope.png\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--root", str(self.dir), "new", "--check", str(f)])
        out = buf.getvalue()
        self.assertIn("CHECK warn · 1 sections · 1 questions (choice 1)", out)
        self.assertIn("ids: a", out)
        self.assertIn("missing asset: nope.png", out)
        self.assertFalse((self.dir / ".2cpc").exists())
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--root", str(self.dir), "new", str(f), "--no-open"])
        self.assertTrue(buf.getvalue().startswith("OK chk v1 · 1 sections"))

    def test_missing_asset_warns(self):
        out = self.run_cli(["new", "T", "--no-open"], "!img nope.png\n")
        self.assertIn("WARN missing asset: nope.png", out)

    def test_next_custom(self):
        out = self.run_cli(["new", "--no-open"],
                           "title: Nx\n# S\n!next impl=Implémenter :: lot 1* ; tests=Écrire les tests ; doc=Doc\n")
        self.assertIn("next: impl tests doc", out)
        html, plan = self.page_plan("nx")
        self.assertEqual(plan["next"]["opts"], ["impl", "tests", "doc"])
        self.assertEqual(plan["next"]["rec"], ["impl"])
        self.assertIn('class="next"', html)
        self.assertIn('data-k="tests"', html)
        self.assertNotIn("{{NEXT}}", html)

    def test_next_default_and_off(self):
        self.run_cli(["new", "--no-open"], "title: Def\nlang: en\n# S\ntext\n")
        _, plan = self.page_plan("def")
        self.assertEqual(plan["next"]["opts"], ["revise", "synth", "tech", "exec"])
        self.assertIn("Start execution", plan["next"]["labels"]["exec"])
        self.run_cli(["new", "--no-open"], "title: Off\nnext: off\n# S\n!next a ; b\n")
        html, plan = self.page_plan("off")
        self.assertIsNone(plan["next"])
        self.assertNotIn('class="next"', html)

    def test_page_inlines_answers_js(self):
        self.run_cli(["new", "--no-open"], SAMPLE)
        html, _ = self.page_plan("demo")
        self.assertIn("window.CPCAnswers", html)
        self.assertLess(html.index("root.CPCAnswers = api"), html.index("var A = window.CPCAnswers"))
        self.assertNotIn("{{ANSWERS_JS}}", html)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_generated_answer_from_real_page(self):
        """End-to-end: the PLAN embedded in a rendered page + the inlined answers.js -> answer text."""
        import subprocess
        self.run_cli(["new", "--no-open"], SAMPLE)
        html, plan = self.page_plan("demo")
        js = html.split("<script>")[2].split("</script>")[0]  # 1: PLAN/I18N, 2: answers.js, 3: app.js
        state = {"a": {"opt": "X", "db": "PG", "f": ["E", "W"], "p": "2", "m": {"R2": "C1"}, "todo": ["t2"]},
                 "o": {}, "c": {}, "n": {"items": [{"k": "exec", "on": True}]}}
        prog = (js + "\nconst A=module.exports, P=" + json.dumps(plan) + ", S=" + json.dumps(state) + ";\n"
                "const t=k=>({yes:'yes',no:'no'})[k]||k;\n"
                "process.stdout.write(A.build(P,S,false,t));\n")
        f = self.dir / "run.js"
        f.write_text(prog, encoding="utf-8")
        out = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.split("\n"), [
            "2CPC demo v1", "opt=X", "db=PG", "f=E,W", "p=2/3", "m=R2:C1", "todo=1/2 ✓t2", "next=exec"])

    def test_new_without_id_does_not_overwrite(self):
        self.run_cli(["new", "--no-open"], SAMPLE)
        out = self.run_cli(["new", "--no-open"], SAMPLE)
        self.assertTrue(out.startswith("OK demo-2 v1"), out)


from cpc import answers as ans_mod  # noqa: E402
from cpc import patch as patch_mod  # noqa: E402

BASE = """title: P
lang: fr
intro: x

# Contexte {#ctx}
Texte A.
!code python
# pas un titre
!end
## Détail
d
# Phase 1
?choice db | Base ? | pg=PostgreSQL* ; lite=SQLite
?approve sc | Scope | A1=Un ; A2=Deux
# Phase 2
?multi f | F | a=Alpha ; b=Beta
?rank r | R | x=X ; y=Y
?text tx | T

!next revise=Revise* ; exec=Exec
"""


class AnchorPatchTest(unittest.TestCase):
    def test_heading_anchor(self):
        p = parse(BASE)
        hs = [(b["id"], b["text"]) for b in p.blocks if b["t"] == "h"]
        self.assertEqual(hs[0], ("ctx", "Contexte"))
        self.assertEqual([h[0] for h in hs], ["ctx", "detail", "phase-1", "phase-2"])

    def test_sections_skip_raw_and_stop_at_next(self):
        secs = patch_mod.sections(BASE)
        self.assertEqual([s["id"] for s in secs], ["ctx", "detail", "phase-1", "phase-2"])
        last = BASE.split("\n")[secs[-1]["start"]:secs[-1]["end"]]
        self.assertFalse(any(ln.startswith("!next") for ln in last))

    def test_replace_keeps_heading_when_body_has_none(self):
        out, n = patch_mod.apply(BASE, "@replace # Phase 1\n?yesno go | Go ?\n")
        self.assertEqual(n, 1)
        self.assertIn("# Phase 1\n?yesno go | Go ?\n\n# Phase 2", out)
        self.assertNotIn("?choice db", out)

    def test_replace_by_anchor_prefix_and_new_heading(self):
        out, _ = patch_mod.apply(BASE, "@replace {#ctx}\n# Contexte v2 {#ctx}\nNouveau.\n")
        self.assertIn("# Contexte v2 {#ctx}\nNouveau.\n\n# Phase 1", out)  # level-1 section includes its ##
        self.assertNotIn("Détail", out)
        out, _ = patch_mod.apply(BASE, "@replace ## Dét\nautre\n")  # unique prefix
        self.assertIn("## Détail\nautre\n", out)

    def test_after_before_delete_append_meta(self):
        out, n = patch_mod.apply(BASE, "@after # Phase 1\n# Phase 1b\nz\n@before #phase-2\n# Phase 1c\n"
                                       "@delete ## Détail\n@append\n# Fin\nok\n@meta intro: neuf\n@meta status: x\n"
                                       .replace("@meta status: x\n", ""))
        self.assertEqual(n, 5)
        heads = [b["text"] for b in parse(out).blocks if b["t"] == "h"]
        self.assertEqual(heads, ["Contexte", "Phase 1", "Phase 1b", "Phase 1c", "Phase 2", "Fin"])
        self.assertIn("intro: neuf", out)
        self.assertLess(out.index("# Fin"), out.index("!next"))

    def test_next_op(self):
        out, _ = patch_mod.apply(BASE, "@next a=A* ; b=B\n")
        self.assertIn("!next a=A* ; b=B", out)
        self.assertNotIn("revise=Revise", out)
        out, _ = patch_mod.apply("# S\nx\n", "@next a=A\n")
        self.assertTrue(out.endswith("x\n\n!next a=A\n"), repr(out))

    def test_errors(self):
        for bad, msg in (("@replace # Nope\nx", "not found"), ("hello\n@delete # Phase 1", "before the first"),
                         ("@replace # Phase\nx", "ambiguous"), ("@after # Phase 1\n", "empty content"),
                         ("@meta foo: 1", "unknown header"), ("", "no @operation")):
            with self.assertRaises(patch_mod.PatchError) as cm:
                patch_mod.apply(BASE, bad)
            self.assertIn(msg, str(cm.exception))

    def test_diff_sections(self):
        new = BASE.replace("Texte A.", "Texte B.").replace("# Phase 2", "# Phase 3")
        changed, added, removed = patch_mod.diff_sections(BASE, new)
        self.assertEqual((changed, added, removed), (["ctx"], ["phase-3"], ["Phase 2"]))


ANSWERS = '''2CPC p v1
db="Mongo, vraiment"
sc.A1=✓
sc.A2=✗ "trop tôt"
f=a,"x, y"
r=y>x
tx="ligne\\nsuite"
#Phase 1="à revoir"
next=revise>"mon étape"
'''


class AnswersTest(unittest.TestCase):
    def test_header(self):
        self.assertEqual(ans_mod.header(ANSWERS), ("p", 1))
        self.assertEqual(ans_mod.header("[2CPC] Réponses au plan interactif « P » (v3, 2026-11-09)\nx=1"), (None, 3))

    def test_parse_compact_and_context(self):
        qs = parse(BASE).questions
        r = ans_mod.parse(ANSWERS, qs)
        self.assertEqual(r["answers"]["db"], '"Mongo, vraiment"')
        self.assertEqual(r["approve"]["sc"], {"A1": "✓", "A2": '✗ "trop tôt"'})
        self.assertEqual(r["comments"], {"Phase 1": "à revoir"})
        self.assertEqual(r["next"], 'revise>"mon étape"')
        ctx = ('[2CPC] Réponses au plan interactif « P » (v1, d)\nIntro : x\n---\n'
               'db(Base)=pg(PostgreSQL)\nsc.A1(Un (1))=✓\nr(R)=y(Y)>x(X)\n')
        r = ans_mod.parse(ctx, qs)
        self.assertEqual(r["answers"]["db"], "pg(PostgreSQL)")
        self.assertEqual(r["approve"]["sc"], {"A1": "✓"})

    def test_decision_rows(self):
        p = parse(BASE)
        rows = ans_mod.decision_rows(p.questions, ANSWERS, ["Phase 1"])
        self.assertEqual(rows, [
            ["Base ?", "*Autre :* Mongo, vraiment"],
            ["Scope", "✓ Un · ✗ Deux (« trop tôt »)"],
            ["F", "Alpha, *Autre :* x, y"],
            ["R", "1. Y › 2. X"],
            ["T", "ligne\nsuite"],
            ["💬 Phase 1", "à revoir"],
        ])


class P1CliTest(CliBase):
    def test_answers_save_decisions_changes_prevq(self):
        self.run_cli(["new", "--no-open"], BASE)
        out = self.run_cli(["answers", "--save"], ANSWERS)
        self.assertIn("OK saved p v1 · 8 line(s)", out)
        self.assertIn("sc.A2", self.run_cli(["answers", "p"]))
        v2 = BASE.replace("Texte A.", "Texte B.").replace("?rank r | R |", "?rank r | R2 |") \
                 .replace("# Phase 1\n", "# Phase 1\n!decisions | Acté\n")
        out = self.run_cli(["new", "--id", "p", "--no-open"], v2)
        self.assertIn("changes vs v1: 3 modified (ctx phase-1 phase-2) · 0 new · 0 removed", out)
        self.assertNotIn("WARN", out)
        html, plan = self.page_plan("p", 2)
        self.assertIn('class="decisions"', html)
        self.assertIn("✓ Un · ✗ Deux", html)
        self.assertIn('id="chgBar"', html)
        self.assertIn('data-sec="chg"', html)
        self.assertIn('data-sec="same"', html)
        self.assertEqual(list(plan["prevQ"]), ["r"])
        self.assertEqual(plan["prevQ"]["r"]["label"], "R")
        _, plan1 = self.page_plan("p", 1)
        self.assertEqual(plan1["prevQ"], {})

    def test_decisions_without_answers_then_save_rebuilds(self):
        self.run_cli(["new", "--no-open"], BASE)
        out = self.run_cli(["new", "--id", "p", "--no-open"], BASE + "!decisions\n")
        self.assertIn("WARN !decisions: no saved answers for v1", out)
        out = self.run_cli(["answers", "p", "--save"], ANSWERS)
        self.assertIn("OK rebuilt v2 (!decisions)", out)
        self.assertIn("1. Y › 2. X", self.page_plan("p", 2)[0])

    def test_answers_errors(self):
        self.run_cli(["new", "--no-open"], BASE)
        with self.assertRaises(SystemExit):
            self.run_cli(["answers", "other", "--save"], ANSWERS)
        with self.assertRaises(SystemExit):
            self.run_cli(["answers", "p"])

    def test_patch_cli(self):
        self.run_cli(["new", "--no-open"], BASE)
        pf = self.dir / "p.patch"
        pf.write_text("@replace ## Détail\nnouveau détail\n", encoding="utf-8")
        out = self.run_cli(["patch", "p", str(pf), "--check"])
        self.assertIn("patch: 1 op(s) OK on v1", out)
        self.assertIn("changes vs v1: 1 modified (detail)", out)
        self.assertFalse((self.dir / ".2cpc" / "p" / "v2").exists())
        out = self.run_cli(["patch", "p", str(pf), "--no-open"])
        self.assertTrue(out.startswith("OK p v2 · patch 1 op(s) · "), out)
        self.assertIn("nouveau détail", (self.dir / ".2cpc" / "p" / "v2" / "plan.txt").read_text(encoding="utf-8"))
        pf.write_text("@delete # Nope\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.run_cli(["patch", "p", str(pf), "--no-open"])
        self.assertFalse((self.dir / ".2cpc" / "p" / "v3").exists())


TODO_PLAN = "title: T\n# S\n!todo build=Compiler **APK** ; test=Tester ; Publier\n?yesno go | Go\n"


class P2CliTest(CliBase):
    def test_todo_keys_state_and_carry_over(self):
        p = parse(TODO_PLAN).questions[0]
        self.assertEqual((p["keys"], p["items"]), (["build", "test", "Publier"], ["Compiler **APK**", "Tester", "Publier"]))
        self.run_cli(["new", "--no-open"], TODO_PLAN)
        out = self.run_cli(["todo", "t", "build", "Publier"])
        self.assertIn("OK todo t v1 · 2/3 done · done: todo.build todo.Publier", out)
        self.assertIn("x todo.build", self.run_cli(["todo", "t"]))
        html, plan = self.page_plan("t")
        self.assertEqual(plan["questions"][0]["agent"], ["Compiler **APK**", "Publier"])
        self.assertIn('value="0" checked disabled', html)
        self.assertIn('data-i18n="agentDone"', html)
        self.run_cli(["new", "--id", "t", "--no-open"], TODO_PLAN.replace("Tester", "Tester encore"))
        _, plan2 = self.page_plan("t", 2)
        self.assertEqual(plan2["questions"][0]["agent"], ["Compiler **APK**", "Publier"])
        self.assertIn("1/3 done · undo: todo.build", self.run_cli(["todo", "t", "build", "--undo"]))
        with self.assertRaises(SystemExit):
            self.run_cli(["todo", "t", "nope"])

    def test_status_header_command_and_list(self):
        self.run_cli(["new", "--no-open"], "title: A\nstatus: brouillon\n# S\n")
        self.run_cli(["new", "--no-open"], "title: B\n# S\n")
        self.assertIn("[draft] A", self.run_cli(["list"]))
        self.assertIn("v1 · ", self.page_plan("a")[0])
        self.assertIn('class="st st-draft">brouillon', self.page_plan("a")[0])
        self.assertEqual(self.run_cli(["status", "b", "archivé"]).strip(), "OK b [archived]")
        out = self.run_cli(["list"])
        self.assertNotIn("] B", out)
        self.assertIn("(1 archived: list --archived)", out)
        self.assertIn("[archived] B", self.run_cli(["list", "--archived"]))
        with self.assertRaises(SystemExit):
            self.run_cli(["status", "b", "bof"])
        self.assertIn("WARN bad status 'bof'", self.run_cli(["new", "--no-open"], "title: C\nstatus: bof\n# S\n"))

    def test_shared_assets_and_gc(self):
        (self.dir / "b.png").write_bytes(b"\x89PNG other")
        for k, img in enumerate(("a.png", "a.png", "b.png", "b.png")):
            self.run_cli(["new", "--no-open"] + (["--id", "g"] if k else []), f"title: G\n# S {k}\n!img {img}\n")
        pdir = self.dir / ".2cpc" / "g"
        self.assertEqual(len(list((pdir / "assets").iterdir())), 2)
        (pdir / "v1" / "assets").mkdir()  # legacy per-version copy
        (pdir / "v1" / "assets" / "old.png").write_bytes(b"x")
        out = self.run_cli(["gc", "--keep", "2"])
        self.assertIn("would delete g/v1/index.html", out)
        self.assertIn("would delete g/v2/index.html", out)
        self.assertIn("would delete g/v1/assets/old.png", out)
        self.assertIn("-a.png", out)
        self.assertNotIn("-b.png", out)
        self.assertIn("DRY RUN · 4 file(s)", out)
        self.assertTrue((pdir / "v1" / "index.html").is_file())
        out = self.run_cli(["gc", "--keep", "2", "--yes"])
        self.assertIn("OK gc · 4 file(s)", out)
        self.assertFalse((pdir / "v1" / "index.html").exists())
        self.assertTrue((pdir / "v1" / "plan.txt").is_file())
        self.assertFalse((pdir / "v1" / "assets").exists())
        self.assertIn('<span class="gone"', self.page_plan("g", 4)[0])
        self.assertIn("DRY RUN · 0 file(s)", self.run_cli(["gc", "--keep", "2"]))
        self.run_cli(["rebuild"])  # gc'd pages stay removed...
        self.assertFalse((pdir / "v1" / "index.html").exists())
        self.run_cli(["rebuild", "g", "--v", "1"])  # ...unless asked
        self.assertTrue((pdir / "v1" / "index.html").is_file())

    def test_legacy_asset_fallback(self):
        self.run_cli(["new", "--no-open"], "title: L\n# S\n!img gone.png\n")
        v1 = self.dir / ".2cpc" / "l" / "v1"
        (v1 / "assets").mkdir()
        (v1 / "assets" / "gone.png").write_bytes(b"legacy")
        out = self.run_cli(["rebuild"])
        self.assertIn("OK rebuilt 1", out)
        self.assertIn("../assets/", (v1 / "index.html").read_text(encoding="utf-8"))


class P3CliTest(CliBase):
    def test_dashboard(self):
        self.run_cli(["new", "--no-open"], TODO_PLAN)
        self.run_cli(["todo", "t", "test"])
        self.run_cli(["answers", "--save"], "2CPC t v1\ngo=oui\n")
        self.run_cli(["new", "--no-open"], "title: Old\nstatus: archived\n# S\n")
        html = (self.dir / ".2cpc" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="t/v1/index.html"', html)
        self.assertIn("<span>1/3</span>", html)
        self.assertIn("Réponses enregistrées</span><span>v1", html)
        self.assertIn('data-total="1"', html)
        self.assertIn("Archivés (1)", html)

    def test_registry_list_all_rebuild_all(self):
        self.run_cli(["new", "--no-open"], "title: One\n# S\n")
        other = Path(tempfile.mkdtemp())
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                cli.main(["--root", str(other), "new", "--no-open", "--file", str(self.write("title: Two\n# S\n"))])
            reg = json.loads((self.home / ".2cpc" / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(len(reg["projects"]), 2)
            out = self.run_cli(["list", "--all"])
            self.assertIn(f"{self.dir.name}/one v1", out)
            self.assertIn(f"{other.name}/two v1", out)
            self.assertIn("OK rebuilt 2", self.run_cli(["rebuild", "--all"]))
        finally:
            shutil.rmtree(other, ignore_errors=True)
        self.assertNotIn("two", self.run_cli(["list", "--all"]))  # dead project skipped

    def test_skill_outdated_warning(self):
        skill = self.home / "SKILL.md"
        skill.write_text("old", encoding="utf-8")
        self.assertIn("WARN skill outdated", self.run_cli(["new", "--no-open"], "title: S\n# S\n"))
        from cpc.skill import render_skill
        skill.write_text(render_skill(ROOT), encoding="utf-8")
        self.assertNotIn("WARN", self.run_cli(["new", "--no-open"], "title: S\n# S\n"))


class P4CliTest(CliBase):
    def test_compare_and_html(self):
        (self.dir / "b.png").write_bytes(b"\x89PNG b")
        (self.dir / "m.html").write_text("<p>maquette</p>", encoding="utf-8")
        out = self.run_cli(["new", "--no-open"], "title: C\n# S\n!compare a.png | b.png | Avant / après\n"
                                                 "!html m.html | 300 | Maquette\n!compare a.png\n!html m.html | big\n")
        self.assertIn("!compare needs", out)
        self.assertIn("!html: bad height 'big'", out)
        html, _ = self.page_plan("c")
        self.assertRegex(html, r'<img src="\.\./assets/[0-9a-f]{8}-a\.png"[^>]*><img class="after" src="\.\./assets/[0-9a-f]{8}-b\.png"')
        self.assertIn('type="range"', html)
        self.assertRegex(html, r'<iframe src="\.\./assets/[0-9a-f]{8}-m\.html" sandbox="allow-scripts"[^>]*height:300px')
        chk = self.write("title: C\n!compare a.png | nope.png\n!html nope.html\n!link X | src/nope.cs:3\n")
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--root", str(self.dir), "new", "--check", str(chk)])
        self.assertEqual(buf.getvalue().count("WARN missing"), 3, buf.getvalue())

    def test_editor_links(self):
        (self.dir / "src").mkdir()
        (self.dir / "src" / "Foo.cs").write_text("x", encoding="utf-8")
        posix = (self.dir / "src" / "Foo.cs").resolve().as_posix()
        body = "# S\n!link Foo | src/Foo.cs:42\n!link Dir | src\n"
        self.run_cli(["new", "--no-open"], "title: E\n" + body)
        html, _ = self.page_plan("e")
        self.assertIn(f'href="vscode://file/{posix}:42:1"', html)
        self.assertIn('class="alt" href="file:', html)
        self.assertIn('🔗 Dir', html)  # directory -> plain file:// link
        self.run_cli(["new", "--no-open"], "title: E2\neditor: idea\n" + body)
        self.assertIn(f'href="idea://open?file={posix}&amp;line=42"', self.page_plan("e2")[0])
        (self.home / ".2cpc").mkdir(parents=True, exist_ok=True)
        (self.home / ".2cpc" / "config.json").write_text('{"editor": "myed://{path}#L{line}"}', encoding="utf-8")
        self.run_cli(["new", "--no-open"], "title: E3\n" + body)
        self.assertIn(f'href="myed://{posix}#L42"', self.page_plan("e3")[0])
        self.run_cli(["new", "--no-open"], "title: E4\neditor: none\n" + body)
        self.assertNotIn("✎", self.page_plan("e4")[0])

    def test_delta_answers_merge(self):
        self.assertTrue(ans_mod.is_delta("2CPC p v2 Δ\nx=1"))
        self.assertFalse(ans_mod.is_delta("2CPC p v2\nx=1"))
        old = '2CPC p v2\ndb(Base)=pg\nsc.A1(Un)=✓\ntx="a"\n#Phase 1="c"\nnext=revise'
        new = ans_mod.merge(old, '2CPC p v2 Δ\ndb=lite\nsc.A2=✗\ntx=\n#Phase 1=\nnext=exec')
        self.assertEqual(new.split("\n"), ["2CPC p v2", "db=lite", "sc.A1(Un)=✓", "next=exec", "sc.A2=✗"])
        self.run_cli(["new", "--no-open"], BASE)
        self.run_cli(["answers", "--save"], ANSWERS)
        out = self.run_cli(["answers", "--save"], "2CPC p v1 Δ\ntx=\nr=x>y\n")
        self.assertIn("OK merged Δ into p v1", out)
        saved = (self.dir / ".2cpc" / "p" / "v1" / "answers.txt").read_text(encoding="utf-8")
        self.assertIn("r=x>y", saved)
        self.assertNotIn("tx=", saved)
        self.assertIn('db="Mongo, vraiment"', saved)


if __name__ == "__main__":
    unittest.main()
