"""SEL-045 Part A item 2: one compensating event after the merge of SEL-041's kept branch.

SEL-041 (9d9caf94) was superseded, so AD-038-R25 discarded its session's four event lines on record (event
dc0f38f4, evidence docs/evidence/2026-11-21_SEL-041_.../discarded_events.jsonl) and nulled the filing a844c156's
claim. Its state change to `completed` could not be walked back (`unreconciled`), so after the discard main's log
said `proposed` while the live graph said `completed`.

SEL-045 merges the branch, and `merge=union` appends those four lines to main's log after the compensation. Their
work is now wanted (the task lands), so they stay: they make the log say `completed`, as the graph does. But in append
order they leave `claimed_by: cc` after the compensation that nulled it. This script appends one evented
`artifact_updated` that sets the claim back to null, the value the live graph holds, so replay of main's log and the
live graph agree on both state and claim. The log is not edited (event sourcing's compensating-event rule, as
seldon/core/kept_events.py cites it).

Run once, from the worktree root: python -m dotenv -f .env run -- env PYTHONPATH=. python docs/evidence/sel045/recompensate_a844c156.py
"""
from pathlib import Path

from seldon.config import get_neo4j_driver, load_project_config
from seldon.core.artifacts import update_artifact

FILING = "a844c156-3a32-4941-aad2-06dcfda3aeaf"
ACTOR = "cc"


def main() -> None:
    config = load_project_config()
    driver = get_neo4j_driver(config)
    try:
        update_artifact(project_dir=Path.cwd(), driver=driver, database=config["neo4j"]["database"],
                        artifact_id=FILING, properties={"claimed_by": None, "claimed_at": None},
                        actor=ACTOR, authority="accepted")
    finally:
        driver.close()
    print(f"compensated claim of {FILING}")


if __name__ == "__main__":
    main()
