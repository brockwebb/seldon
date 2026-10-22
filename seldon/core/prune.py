"""The weekly prune (PRUNE-001): close what is already fixed, re-date or withdraw stale FUTURE ideas.

**Why.** Squiddy's CLAUDE.md puts maintenance in scope as "scheduled stages with gates ... never
unbounded agents. The weekly sweep is the template." The prior art the task cites is L. Weathers,
"SHIP" (2026-07-01): deprecation as a scheduled event, because a store that never lets anything die
cannot tell the living from the dead. Before PRUNE-001 squiddy held 56 open Issues, most of which
said FIXED in their own first clause; nothing ever read that clause.

**The sweep never deletes.** It resolves an Issue, re-dates a proposal, withdraws one with its
reason, or leaves it alone. Every write goes through the ordinary write paths
(`transition_state`, `update_artifact`, `transition_task`), so each one is an event in the
repository's own store and a node change in its own database.

**Rule 1, fixed issues.** An open or in-progress Issue is resolved when either holds:

- *fixed_marker*: one of `prune.fixed_markers` appears in the first `prune.lead_chars` characters
  of its description, and the first such marker is not preceded within
  `prune.negation_window_words` words by one of `prune.negations`. The lead is where these records state their status ("S-008 defect 1, FIXED
  with its test ..."); a marker deeper in the text describes a sub-finding ("R-23's provenance
  defect, CLOSED ... CONDITION (3), NOT FIXED") and does not close the whole Issue. The negation
  guard is what keeps "K-001 finding 2, NOT FIXED" and "MEASURED not fixed" open.
- *fixed_commit*: the text names a commit in a fix phrase ("fixed in <sha>", "resolved by <sha>")
  and that commit is an ancestor of the repository's branch. A bare commit id is NOT enough:
  issues name the commit where a defect was seen far more often than the one that fixed it. A
  named fix commit the branch does not hold keeps the Issue open, whatever its lead says.

The reason recorded is the commit: the named one for fixed_commit, else the branch head at the
moment the Issue was filed, since an Issue whose own text says FIXED was filed after its fix.

**Rule 2, stale FUTURE proposals.** A `proposed` ResearchTask whose description carries
TRIAGE-001's FUTURE prefix (`seldon.core.moving.is_future`) is stale when its clock (`redated_at`,
else `created_at`) is at least `prune.stale_days` old. A stale one with an edge to or from an open
ResearchTask is re-dated (open work names it, so its trigger is live); one with no such edge is
withdrawn with `prune.withdraw_reason`. Judging whether a trigger is plausible is a hand step
(`seldon prune redate`); the lane makes zero model calls and so cannot, and the hand re-date resets
the clock for another `stale_days`.

**Spend (DN-042).** The lane carries a token cap and stops at `token_stop_factor` times it
(R-178: +20 percent stops). The sweep makes no model calls, so the cap is 0 and the guard exists
to stop the lane the moment any rule starts charging tokens it did not declare.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from seldon.core.moving import is_future

#: The event one run of the sweep writes to the lane owner's store, whatever it found.
EVENT_PRUNE_PASS = "prune_pass"

#: Who the lane's writes are attributed to in every repository's event store.
PRUNE_ACTOR = "prune"

#: Every key `prune:` in seldon.yaml must carry. No defaults: a rule whose threshold is
#: guessed is the defect PRUNE-001 exists to stop (doctrine section 2, never hardcode).
REQUIRED_KEYS = ("repositories", "branch", "stale_days", "fixed_markers", "negations",
                 "negation_window_words", "lead_chars", "fix_verbs", "withdraw_reason",
                 "token_cap", "token_stop_factor")

#: Issue states the sweep may resolve: the domain machine allows `resolved` from these two.
RESOLVABLE_ISSUE_STATES = ("open", "in_progress")

#: Issue states counted as open (`seldon issue list --open`).
OPEN_ISSUE_STATES = ("open", "in_progress", "blocked")

#: ResearchTask states that count as open work for rule 2's edge test.
OPEN_TASK_STATES = ("proposed", "accepted", "in_progress", "blocked")

#: A commit id as written in issue prose: 7 to 40 hex characters.
SHA_RE = r"[0-9a-f]{7,40}"


class PruneConfigError(ValueError):
    """`prune:` in seldon.yaml is missing or malformed."""


class PruneCeiling(RuntimeError):
    """The lane's token ceiling was crossed (DN-042 R-178)."""


def load_prune_config(config: dict) -> dict:
    """The `prune:` block of a parsed seldon.yaml, validated.

    Args:
        config: Parsed seldon.yaml of the lane's owning project.

    Returns:
        The block, with `fixed_markers`, `negations` and `fix_verbs` lower-cased.

    Raises:
        PruneConfigError: If the block or any required key is missing, or a value has the wrong type.
    """
    block = (config or {}).get("prune")
    if not isinstance(block, dict):
        raise PruneConfigError("seldon.yaml has no `prune:` block; the weekly prune refuses to guess its rules")
    missing = [k for k in REQUIRED_KEYS if k not in block]
    if missing:
        raise PruneConfigError(f"seldon.yaml prune block missing {missing}")
    for key in ("stale_days", "negation_window_words", "lead_chars"):
        v = block[key]
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise PruneConfigError(f"prune.{key} must be a positive integer, got {v!r}")
    for key in ("repositories", "fixed_markers", "negations", "fix_verbs"):
        v = block[key]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
            raise PruneConfigError(f"prune.{key} must be a non-empty list of strings, got {v!r}")
    cap, factor = block["token_cap"], block["token_stop_factor"]
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise PruneConfigError(f"prune.token_cap must be a non-negative integer, got {cap!r}")
    if isinstance(factor, bool) or not isinstance(factor, (int, float)) or factor < 1:
        raise PruneConfigError(f"prune.token_stop_factor must be a number >= 1, got {factor!r}")
    if not isinstance(block["withdraw_reason"], str) or "{days}" not in block["withdraw_reason"]:
        raise PruneConfigError("prune.withdraw_reason must be a string containing {days}")
    out = dict(block)
    for key in ("fixed_markers", "negations", "fix_verbs"):
        out[key] = [x.lower() for x in block[key]]
    return out


class SpendGuard:
    """DN-042's band for one lane run: charge tokens, stop past `cap * factor`.

    Args:
        cap: The declared tokens for one run.
        factor: The stop band (1.2 is R-178's +20 percent).
    """

    def __init__(self, cap: int, factor: float):
        self.cap = cap
        self.factor = factor
        self.spent = 0

    @property
    def ceiling(self) -> float:
        return self.cap * self.factor

    def charge(self, tokens: int) -> None:
        """Record tokens spent by a unit of the sweep. Raises PruneCeiling past the band."""
        self.spent += int(tokens)
        self.check()

    def check(self) -> None:
        """Raises:
            PruneCeiling: When spend so far exceeds `cap * factor`.
        """
        if self.spent > self.ceiling:
            raise PruneCeiling(f"prune token ceiling crossed: spent {self.spent} > cap {self.cap} x "
                               f"{self.factor} (DN-042 R-178)")


# ── rule 1: fixed issues ────────────────────────────────────────────────────────────────────────

def _negated(text: str, start: int, cfg: dict) -> bool:
    """True when one of `cfg["negations"]` is among the words just before position `start`."""
    before = re.findall(r"[A-Za-z']+", text[:start])[-cfg["negation_window_words"]:]
    return any(w.lower() in cfg["negations"] for w in before)


def fixed_marker(text: Optional[str], cfg: dict) -> Optional[str]:
    """The fixed marker an Issue description's lead opens with, as written, or None when negated.

    Args:
        text: The Issue's description.
        cfg: A validated prune config.

    Returns:
        The marker as it appears in the text (e.g. "FIXED"), or None.
    """
    lead = (text or "")[: cfg["lead_chars"]]
    alternatives = "|".join(re.escape(m) for m in cfg["fixed_markers"])
    # The FIRST marker decides. A status lead is stated once, so a later marker in the lead is
    # prose about something else: "HV-002 finding 2, NOT FIXED ... attach a RESOLVED CANDIDATE"
    # (squiddy dc636a65) is open, and taking any un-negated marker would have closed it.
    m = re.search(rf"\b({alternatives})\b", lead, flags=re.IGNORECASE)
    if m is None or _negated(lead, m.start(), cfg):
        return None
    return m.group(1)


def fixed_commit_named(text: Optional[str], cfg: dict) -> Optional[str]:
    """The commit id an Issue names in a fix phrase ("fixed in abc1234"), or None.

    Args:
        text: The Issue's description (and resolution notes, if the caller joins them).
        cfg: A validated prune config.

    Returns:
        The commit id as written, or None.
    """
    markers = "|".join(re.escape(m) for m in cfg["fixed_markers"])
    verbs = "|".join(re.escape(v) for v in cfg["fix_verbs"])
    pattern = rf"\b(?:{markers})\s+(?:{verbs})\s+(?:commit\s+)?`?({SHA_RE})\b"
    for m in re.finditer(pattern, text or "", flags=re.IGNORECASE):
        if not _negated(text, m.start(), cfg):
            return m.group(1).lower()
    return None


class Git:
    """The two git questions rule 1 asks of a repository. A class so tests can plant answers."""

    def __init__(self, repo: Path):
        self.repo = Path(repo)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True)

    def on_branch(self, sha: str, branch: str) -> bool:
        """True when `sha` resolves to a commit that is an ancestor of `branch`."""
        resolved = self._run("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
        if resolved.returncode != 0:
            return False
        r = self._run("merge-base", "--is-ancestor", resolved.stdout.strip(), branch)
        if r.returncode not in (0, 1):
            raise RuntimeError(f"git merge-base failed in {self.repo}: {r.stderr.strip()}")
        return r.returncode == 0

    def head_at(self, branch: str, when_iso: str) -> Optional[str]:
        """The commit `branch` pointed at, by commit date, at `when_iso`; None before its first commit."""
        r = self._run("rev-list", "-1", f"--before={when_iso}", branch)
        if r.returncode != 0:
            raise RuntimeError(f"git rev-list failed in {self.repo}: {r.stderr.strip()}")
        return r.stdout.strip()[:12] or None


def issue_decision(issue: dict, cfg: dict, git: Git) -> Optional[dict]:
    """Rule 1 for one Issue row: a resolve decision, or None to leave it alone.

    Args:
        issue: Row with `artifact_id`, `state`, `description`, `created_at`.
        cfg: A validated prune config.
        git: Git access for the Issue's repository.

    Returns:
        `{"artifact_id", "rule", "evidence", "commit", "resolution_notes"}`, or None.
    """
    if issue.get("state") not in RESOLVABLE_ISSUE_STATES:
        return None
    text = issue.get("description") or ""
    named = fixed_commit_named(text, cfg)
    if named:
        # A fix the Issue names but the branch does not hold has not landed (an unmerged branch,
        # a rebased-away commit): it stays open whatever its lead says.
        if not git.on_branch(named, cfg["branch"]):
            return None
        rule, evidence, commit = "fixed_commit", f"names {named}, an ancestor of {cfg['branch']}", named
    else:
        marker = fixed_marker(text, cfg)
        if marker is None:
            return None
        commit = git.head_at(cfg["branch"], issue.get("created_at") or "")
        rule = "fixed_marker"
        evidence = f"its own text says {marker!r} in its first {cfg['lead_chars']} characters"
        if commit is None:
            return None
    notes = (f"PRUNE-001 weekly prune, rule {rule}: {evidence}. Fixed as of {commit}"
             + (" (the named commit)." if rule == "fixed_commit"
                else f" ({cfg['branch']} when the issue was filed)."))
    return {"artifact_id": issue["artifact_id"], "rule": rule, "evidence": evidence,
            "commit": commit, "resolution_notes": notes}


# ── rule 2: stale FUTURE proposals ──────────────────────────────────────────────────────────────

def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def proposal_decision(task: dict, cfg: dict, now: datetime) -> Optional[dict]:
    """Rule 2 for one ResearchTask row: re-date, withdraw, or None to leave it alone.

    Args:
        task: Row with `artifact_id`, `state`, `description`, `created_at`, `redated_at`,
            and `open_neighbours` (ids of open ResearchTasks with an edge to or from it).
        cfg: A validated prune config.
        now: The run's clock.

    Returns:
        `{"artifact_id", "action": "redate"|"withdraw", "reason", "age_days"}`, or None.
    """
    if task.get("state") != "proposed" or not is_future(task.get("description")):
        return None
    clock = task.get("redated_at") or task.get("created_at")
    if not clock:
        return None
    age = (now - _parse_iso(clock)).days
    if age < cfg["stale_days"]:
        return None
    neighbours = sorted(task.get("open_neighbours") or [])
    if neighbours:
        reason = (f"PRUNE-001: stale {age} days but open task(s) "
                  f"{', '.join(n[:8] for n in neighbours)} point at it, so its trigger is live")
        return {"artifact_id": task["artifact_id"], "action": "redate", "reason": reason, "age_days": age}
    return {"artifact_id": task["artifact_id"], "action": "withdraw",
            "reason": cfg["withdraw_reason"].format(days=cfg["stale_days"]), "age_days": age}


# ── reading a repository's graph ────────────────────────────────────────────────────────────────

ISSUES_QUERY = ("MATCH (i:Issue) RETURN i.artifact_id AS artifact_id, i.state AS state, "
                "i.name AS name, i.description AS description, i.created_at AS created_at")

TASKS_QUERY = (
    "MATCH (t:ResearchTask) "
    "OPTIONAL MATCH (t)-[]-(o:ResearchTask) WHERE o.state IN $open "
    "WITH t, collect(DISTINCT o.artifact_id) AS open_neighbours "
    "RETURN t.artifact_id AS artifact_id, t.state AS state, t.description AS description, "
    "       t.created_at AS created_at, t.redated_at AS redated_at, open_neighbours")


def read_rows(driver, database: str) -> tuple[list[dict], list[dict]]:
    """Every Issue and every ResearchTask row the two rules read, in two queries.

    Returns:
        `(issues, tasks)`.
    """
    with driver.session(database=database) as s:
        issues = s.run(ISSUES_QUERY).data()
        tasks = s.run(TASKS_QUERY, open=list(OPEN_TASK_STATES)).data()
    return issues, tasks


def counts(issues: Iterable[dict], tasks: Iterable[dict], cfg: dict, now: datetime) -> dict:
    """The numbers PRUNE-001 reports before and after, per repository."""
    issues, tasks = list(issues), list(tasks)
    future = [t for t in tasks if t.get("state") == "proposed" and is_future(t.get("description"))]
    stale = [t for t in future
             if (t.get("redated_at") or t.get("created_at"))
             and (now - _parse_iso(t.get("redated_at") or t["created_at"])).days >= cfg["stale_days"]]
    return {"open_issues": sum(1 for i in issues if i.get("state") in OPEN_ISSUE_STATES),
            "proposed_tasks": sum(1 for t in tasks if t.get("state") == "proposed"),
            "future_proposed": len(future),
            "stale_future": len(stale)}


# ── one repository ──────────────────────────────────────────────────────────────────────────────

def prune_repository(repo: Path, driver, database: str, domain_config, cfg: dict, now: datetime,
                     dry_run: bool, guard: SpendGuard, session_id: Optional[str] = None,
                     git: Optional[Git] = None,
                     echo: Callable[[str], None] = lambda s: None) -> dict:
    """Run both rules over one repository's graph and apply the decisions.

    Args:
        repo: The repository root (its event store receives every write).
        driver: Neo4j driver.
        database: The repository's database.
        domain_config: The repository's domain config (state machines).
        cfg: A validated prune config.
        now: The run's clock.
        dry_run: Decide and report; write nothing.
        guard: The run's spend guard, checked before each write.
        session_id: Recorded on every event.
        git: Git access for `repo` (tests plant one).
        echo: Progress line sink.

    Returns:
        `{"repo", "before", "after", "resolved", "redated", "withdrawn", "errors"}`; each action
        list holds the decisions taken. A failed write is a row in `errors`, never a crash that
        takes the completed writes with it (doctrine section 15.7).
    """
    from seldon.core.artifacts import commit_writes, plan_state_change, plan_update_artifact, transition_task

    git = git or Git(repo)
    issues, tasks = read_rows(driver, database)
    before = counts(issues, tasks, cfg, now)
    out = {"repo": str(repo), "database": database, "before": before,
           "resolved": [], "redated": [], "withdrawn": [], "errors": []}

    for issue in issues:
        decision = issue_decision(issue, cfg, git)
        if decision is None:
            continue
        guard.check()
        echo(f"  resolve {decision['artifact_id'][:8]} ({decision['rule']}, {decision['commit']})")
        try:
            if not dry_run:
                # The note and the resolution go down in one ledger append, the
                # transition validated before it (SEL-007): no resolved-without-note
                # or note-without-resolution Issue is left behind by an error row.
                commit_writes(repo, driver, database, [
                    plan_update_artifact(project_dir=repo, driver=driver, database=database,
                                         artifact_id=decision["artifact_id"],
                                         properties={"resolution_notes": decision["resolution_notes"]},
                                         actor=PRUNE_ACTOR, authority="accepted", session_id=session_id),
                    plan_state_change(domain_config=domain_config, artifact_id=decision["artifact_id"],
                                      artifact_type="Issue", current_state=issue["state"],
                                      new_state="resolved", actor=PRUNE_ACTOR, authority="accepted",
                                      session_id=session_id),
                ])
            out["resolved"].append(decision)
        except Exception as exc:                                    # noqa: BLE001 — recorded as a row
            out["errors"].append({"artifact_id": decision["artifact_id"], "action": "resolve",
                                  "error": f"{type(exc).__name__}: {exc}"})

    for task in tasks:
        decision = proposal_decision(task, cfg, now)
        if decision is None:
            continue
        guard.check()
        echo(f"  {decision['action']} {decision['artifact_id'][:8]} (age {decision['age_days']} d)")
        try:
            if not dry_run:
                if decision["action"] == "redate":
                    redate(repo, driver, database, decision["artifact_id"], decision["reason"],
                           now, session_id)
                else:
                    transition_task(project_dir=repo, driver=driver, database=database,
                                    domain_config=domain_config, artifact_id=decision["artifact_id"],
                                    current_state="proposed", new_state="withdrawn",
                                    actor=PRUNE_ACTOR, authority="accepted", session_id=session_id,
                                    terminal_reason=decision["reason"])
            out["redated" if decision["action"] == "redate" else "withdrawn"].append(decision)
        except Exception as exc:                                    # noqa: BLE001 — recorded as a row
            out["errors"].append({"artifact_id": decision["artifact_id"], "action": decision["action"],
                                  "error": f"{type(exc).__name__}: {exc}"})

    if dry_run:
        out["after"] = before
    else:
        issues, tasks = read_rows(driver, database)
        out["after"] = counts(issues, tasks, cfg, now)
    return out


def redate(repo: Path, driver, database: str, artifact_id: str, reason: str, now: datetime,
           session_id: Optional[str] = None, actor: str = PRUNE_ACTOR) -> None:
    """Keep a FUTURE proposal alive for another `stale_days`: set `redated_at` and `redate_reason`.

    Args:
        repo: The repository whose event store records the update.
        driver: Neo4j driver.
        database: The repository's database.
        artifact_id: The task.
        reason: One line, why it was kept.
        now: The new clock value.
        session_id: Recorded on the event.
        actor: Who re-dated it (`prune` for the lane, the CLI actor for a hand re-date).
    """
    from seldon.core.artifacts import update_artifact

    update_artifact(project_dir=repo, driver=driver, database=database, artifact_id=artifact_id,
                    properties={"redated_at": now.isoformat().replace("+00:00", "Z"),
                                "redate_reason": reason},
                    actor=actor, authority="accepted", session_id=session_id)


def total_actions(results: Iterable[dict]) -> int:
    """How many writes a run decided across its repositories (the notification gate)."""
    return sum(len(r["resolved"]) + len(r["redated"]) + len(r["withdrawn"]) + len(r["errors"])
               for r in results)
