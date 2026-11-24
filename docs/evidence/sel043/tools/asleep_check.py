"""SEL-043 Part D, real data: the power log's sleep inside SQ-133R's gate (96c1e285) against wall minus monotonic."""
from seldon.core import stations as S

text = S.power_log_text()
first = next((l[:25] for l in (text or "").splitlines() if l[:4].isdigit()), None)
print("power log first line:", first)
start, end, mono = "2026-11-13T17:38:06Z", "2026-11-13T20:38:40Z", 7734.619
asleep = S.asleep_seconds(start, end, text)
wall = S.wall_fields(start, end, mono)
print("wall seconds:", wall["wall_seconds"], "monotonic:", mono, "wall - monotonic:", round(wall["wall_seconds"] - mono, 1))
print("asleep by the power log:", asleep)
