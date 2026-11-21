"""SEL-041 Part A: why every module change selects the whole suite: the import hubs."""
import contextlib
import io
import runpy
import sys

sys.argv = ["replay.py"] + sys.argv[1:4]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path("/tmp/sel041/replay.py")
tf, counts, TOTAL = g["test_files"], g["counts"], g["TOTAL"]
conftest = g["conftest"]
pkg = sys.argv[3]
print(sys.argv[1], "conftest closure:", len(conftest), "modules;",
      sorted(m for m in conftest if not m.startswith("tests"))[:12])
mods = [m for m in g["modules"] if m.startswith(pkg)]
v = sorted(sum(counts[f] for f, cl in tf.items() if m in cl) / TOTAL for m in mods)
print("modules", len(mods), "median share of suite depending on a module:", round(v[len(v) // 2], 2),
      "modules under 25%:", sum(x < .25 for x in v))
tf2 = {f: g["closure"](g["modname"](g["os"].path.join(g["ROOT"], f))) for f in counts}
v2 = sorted(sum(counts[f] for f, cl in tf2.items() if m in cl) / TOTAL for m in mods)
print("  without conftest's closure: median", round(v2[len(v2) // 2], 2), "under 25%:", sum(x < .25 for x in v2))
big = [m for m in mods if len(g["closure"](m) & set(mods)) > 0.8 * len(mods)]
print("  modules whose own closure is >80% of the package:", len(big), sorted(big)[:15])
