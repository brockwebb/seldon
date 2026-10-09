"""MODEL-001 Part A: classify every inventory hit (scratch tool; the table it writes is the record)."""
import collections
import re
import sys
from pathlib import Path

HITS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
ROOT = Path("/Users/brock/GitHub")

MODEL_ID = re.compile(r"claude-(opus|sonnet|haiku|fable)-[0-9]")
ALIAS_VALUE = re.compile(r"""(alias|model|model_id|parse_model|triage_model|default_model)\s*[:=]\s*['"]?(opus|sonnet|haiku|fable)\b""")
CALL = re.compile(r"""claude -p|["']-p["']|["']--print["']|subprocess|Popen|\.messages\.create|model\s*=\s*[A-Za-z_"']|cmd\s*\+?=|\[\s*["']claude|resolve_cli|cli_path|cfg\.get\(["']cli""")

# Paths whose content is a sealed record, a Result, evidence or a ledger (never edited).
HISTORY_PATH = re.compile(
    r"(/|^)(evidence|results?|runs?|outputs?|logs?|audits?|events|ledger|checkpoints?|handoffs|"
    r"snapshots?|archive|reports?|raw|data|paper|figures|governed/ledger|graphs/[^/]+/(ledger|evidence|"
    r"extract/(runs|out|checkpoints)))(/|$)|_RESULT\.md$|seldon_events|\.jsonl$|\.csv$|\.tsv$|\.log$|"
    r"\.json$|\.txt$|\.html$|\.qmd$|\.patch$|\.superseded$|\.corrupt")
# Repositories whose every hit is history for a stated reason.
HISTORY_REPO = {
    "seldon-sel004": "stale clone of seldon on feat/SEL-004, merged 3b4bf21; seldon itself carries the live copy",
    "brock_projects": "audit run manifests: sealed records of completed audit runs",
    "workbench": "2026-10-03 audit-and-decision probe synthesis: a sealed record",
}
# Not Claude model references: the pattern matched an unrelated use.
FALSE_POSITIVE = [
    (re.compile(r"trustgraph-fork/.*(-m', '--model'|'--model',$|cli_version|roles|iam)"), "TrustGraph CLI flag / IAM roles / build version, not a Claude model"),
    (re.compile(r"trustgraph-fork/(Makefile|install_trustgraph\.sh|specs/)"), "TrustGraph build or IAM schema"),
    (re.compile(r"watermarks-remover/"), "image/text watermark tools' own --model flag (Ollama/OpenAI-compatible), not Claude"),
    (re.compile(r"TickBiteRisk/"), "geospatial model-name flag, not Claude"),
    (re.compile(r"(add_alias|remove_alias|_by_alias|alias: typed|exact_alias|adding alias|removing alias|alias: \{|per-alias|\{alias: why\})", re.I), "vocabulary or exercise alias, not a model alias"),
    (re.compile(r"(workflow_roles|for role in roles|if roles:|if not roles:|resolved_roles|roles: list\[str\]|muscle_attribution)"), "workflow/IAM/UI roles, not model roles"),
    (re.compile(r"usai-harness/usai_harness/(cli|setup_commands)\.py"), "USAi harness's own --model/--models flags (USAi gateway catalog, not the Claude CLI)"),
]
OTHER_PROVIDER = re.compile(r"^(usai-harness|usai-api-tester)/")
API_SDK_REPOS = {"census-mcp-server", "federal-survey-concept-mapper"}


def classify(path: str, line: str) -> tuple[str, str]:
    repo = path.split("/", 1)[0]
    rel = path.split("/", 1)[1] if "/" in path else path
    if repo in HISTORY_REPO:
        return "history", HISTORY_REPO[repo]
    for pat, why in FALSE_POSITIVE:
        if pat.search(path + ":" + line) or pat.search(line):
            return "false_positive", why
    if "/cc_tasks/" in "/" + path or rel.startswith("cc_tasks/"):
        if path.endswith("_RESULT.md"):
            return "history", "task RESULT"
        stem = (ROOT / path).with_suffix("")
        if Path(str(stem) + "_RESULT.md").exists() or "ADDENDUM" in path:
            if re.search(r"\*\*Model:\*\*", line):
                return "history", "Model header of an executed task (RESULT exists)"
            return "history", "executed task file (RESULT exists)"
        if re.search(r"\*\*Model:\*\*", line) or (re.search(r"--model\s+\S", line)):
            return "task_header", "open task: Model header or --model in a code block"
        return "history", "task prose citing a model (R5: prose is not checked)"
    if HISTORY_PATH.search(rel):
        return "history", "sealed record, evidence, ledger or data"
    if re.search(r"(^|/)tests?/", rel):
        return "fixture", "test fixture"
    if rel.endswith((".md", ".rst")):
        return "history", "prose (design note, README, prompt); R5: prose is not checked"
    if OTHER_PROVIDER.search(path):
        return "config", "USAi gateway catalog id (different provider; outside the Claude lock)"
    if re.search(r"costs?\[|\[\"costs\"\]|_key = \"claude", line):
        return "history", "key into a sealed study's recorded cost results"
    if repo in API_SDK_REPOS and MODEL_ID.search(line):
        return ("launcher" if CALL.search(line) else "config"), "Anthropic Messages API (SDK), not the CLI"
    is_code = rel.endswith((".py", ".sh", ".js"))
    if is_code and re.search(r"(raise |print\(|logger\.|f\"|f'|help=|description=)", line) and not re.search(r"[\"']--model[\"']\s*,|cmd", line):
        return "false_positive", "message or help text naming the CLI or a model; the call is elsewhere"
    if is_code and re.search(r"costs?\[|\[\"costs\"\]|_key = \"claude", line):
        return "history", "key into a sealed study's recorded cost results"
    if is_code and re.search(r"[\"']--model[\"']\s*,|[\"']--print[\"']", line):
        return "launcher", "passes --model to a model call"
    if is_code and re.search(r"^\s*#|^\s*\"\"\"|^\s*'''", line.split(":", 0)[0] if False else line) and not CALL.search(line):
        return "history", "comment/docstring citing a model"
    if is_code and CALL.search(line) and ("--model" in line or "claude -p" in line or "model=" in line
                                          or "cli" in line or "--print" in line):
        if re.search(r"claude -p", line) and not re.search(r"\[|cmd|subprocess|Popen", line):
            return "history", "comment/docstring/message naming the CLI"
        return "launcher", "makes or composes a model call"
    if is_code and (MODEL_ID.search(line) or "--model" in line or "ANTHROPIC_DEFAULT_" in line):
        return "config", "code default or constant naming a model"
    if MODEL_ID.search(line) or ALIAS_VALUE.search(line) or re.search(r"cli_path|cli_version|roles:|alias:", line):
        if re.search(r"^\s*#", line):
            return "history", "config comment citing a model"
        return "config", "config value naming a model, alias, role map or CLI pin"
    return "history", "other mention"


rows = collections.defaultdict(list)  # class -> rows
per_file_hist = collections.OrderedDict()
for raw in HITS.read_text(errors="replace").splitlines():
    parts = raw.split(":", 2)
    if len(parts) < 3 or not parts[1].isdigit():
        continue
    path, ln, text = parts
    cls, why = classify(path, text)
    if cls in ("history", "false_positive"):
        key = (cls, path, why)
        if key not in per_file_hist:
            per_file_hist[key] = [int(ln), 0]
        per_file_hist[key][1] += 1
    else:
        rows[cls].append((path, int(ln), why, text.strip()[:140]))

counts_lines = collections.Counter()
counts_files = collections.defaultdict(set)
for cls, rs in rows.items():
    counts_lines[cls] += len(rs)
    for r in rs:
        counts_files[cls].add(r[0])
for (cls, path, why), (first, n) in per_file_hist.items():
    counts_lines[cls] += n
    counts_files[cls].add(path)

esc = lambda s: s.replace("|", "\\|").replace("`", "'")
out = []
out.append("# MODEL-001 Part A: model call site and model reference inventory\n")
out.append("**Task:** `cc_tasks/2026-10-09_MODEL-001_config_driven_model_selection.md` (ResearchTask `6efdd767`). "
           "**Governing:** AD-035. **Date:** 2026-10-09.\n")
out.append("**Search.** Every repository under `/Users/brock/GitHub` (36 directories), excluding `.venv`, `venv`, "
           "`node_modules`, `.git`, `.worktrees`, `build`, and files over 5 MB (the single unbounded run stalled on "
           "large data files and was rerun per repository). Patterns: `--model`, `claude -p`, `model_client`, "
           "`alias:`, `roles:`, `ANTHROPIC_DEFAULT_`, `ANTHROPIC_SMALL_FAST_MODEL`, `cli_path`, `cli_version`, and "
           "the regex `claude-(opus|sonnet|haiku|fable)-[0-9]`. Tool: ripgrep, `--hidden`.\n")
out.append("**Classes.** `launcher` makes a call; `config` names a model; `task_header` is an open task's "
           "`**Model:**` header or code-block `--model`; `history` is a sealed record, Result, ledger, evidence "
           "or prose citing what happened (never edited, AD-035 R5 and R7). Two classes are added because the "
           "four do not cover them, and forcing them in would misstate them: `fixture` (a test planting a value) "
           "and `false_positive` (the pattern matched something that is not a Claude model reference, for "
           "example IAM `roles:` or an Ollama `--model` flag).\n")
out.append("**Granularity.** `launcher`, `config`, `task_header` and `fixture` rows are one per line. `history` and "
           "`false_positive` rows are one per file, with the first matching line and the count, because 99 percent "
           "of hits are ledger and evidence lines that no task edits.\n")
out.append("## Counts by class\n")
out.append("| class | lines | files |\n|---|---:|---:|")
for cls in ("launcher", "config", "task_header", "fixture", "history", "false_positive"):
    out.append(f"| {cls} | {counts_lines[cls]} | {len(counts_files[cls])} |")
out.append(f"| **total** | {sum(counts_lines.values())} | {len(set().union(*counts_files.values()))} |\n")

repos = sorted({r[0].split('/')[0] for rs in rows.values() for r in rs} |
               {k[1].split('/')[0] for k in per_file_hist})
out.append("## Counts by repository and class (lines)\n")
out.append("| repo | launcher | config | task_header | fixture | history | false_positive |\n|---|---:|---:|---:|---:|---:|---:|")
by_repo = collections.defaultdict(collections.Counter)
for cls, rs in rows.items():
    for r in rs:
        by_repo[r[0].split('/')[0]][cls] += 1
for (cls, path, why), (first, n) in per_file_hist.items():
    by_repo[path.split('/')[0]][cls] += n
for repo in repos:
    c = by_repo[repo]
    out.append(f"| {repo} | {c['launcher']} | {c['config']} | {c['task_header']} | {c['fixture']} | {c['history']} | {c['false_positive']} |")
out.append("")
for cls in ("launcher", "config", "task_header", "fixture"):
    out.append(f"## {cls}\n")
    out.append("| file:line | why | text |\n|---|---|---|")
    for path, ln, why, text in sorted(rows[cls]):
        out.append(f"| `{path}:{ln}` | {esc(why)} | `{esc(text)}` |")
    out.append("")
for cls in ("history", "false_positive"):
    out.append(f"## {cls} (one row per file: first line, count)\n")
    out.append("| file:line | count | why |\n|---|---:|---|")
    for (c2, path, why), (first, n) in sorted(per_file_hist.items(), key=lambda kv: kv[0][1]):
        if c2 == cls:
            out.append(f"| `{path}:{first}` | {n} | {esc(why)} |")
    out.append("")
OUT.write_text("\n".join(out) + "\n")
print(dict(counts_lines))
