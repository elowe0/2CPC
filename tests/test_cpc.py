import io
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
from cpc import charts  # noqa: E402

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


class CliTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "a.png").write_bytes(b"\x89PNG fake")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

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

    def test_new_and_version(self):
        out = self.run_cli(["new", "--no-open"], SAMPLE + "!img a.png | pic\n")
        self.assertTrue(out.startswith("OK demo v1"), out)
        v1 = self.dir / ".2cpc" / "demo" / "v1"
        html = (v1 / "index.html").read_text(encoding="utf-8")
        self.assertIn("window.PLAN=", html)
        self.assertIn('src="assets/a.png"', html)
        self.assertTrue((v1 / "assets" / "a.png").is_file())
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

    def test_new_without_id_does_not_overwrite(self):
        self.run_cli(["new", "--no-open"], SAMPLE)
        out = self.run_cli(["new", "--no-open"], SAMPLE)
        self.assertTrue(out.startswith("OK demo-2 v1"), out)


if __name__ == "__main__":
    unittest.main()
