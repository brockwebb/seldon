"""SEL-039: every library receipt in every sibling's design notes, counted by the graph it names (none = the default)."""
import collections
import glob
import re

RE = re.compile(r'library receipt: query "[^"]+" \| (?:graph (\S+) \| )?release')
by = collections.Counter()
where = collections.defaultdict(set)
for f in glob.glob("/Users/brock/GitHub/*/docs/design/**/*.md", recursive=True):
    repo = f.split("/")[4]
    for line in open(f, encoding="utf-8", errors="replace"):
        m = RE.search(line)
        if m:
            g = m.group(1) or "(none)"
            by[(repo, g)] += 1
            where[(repo, g)].add(f.split("/docs/design/")[1])
for k, v in sorted(by.items()):
    print(k, v, sorted(where[k])[:4] if k[1] != "(none)" else "")
