#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""round_guard.py — Multi-round self-check state machine.

Governs the loop protocol of the self_check skill:

  streak rule   : a round with ANY issue found resets streak to 0, even if the
                  issues were fixed within the same round. Only rounds that
                  found zero issues increment streak. Loop ends (DONE) when
                  streak >= 3 — i.e. three consecutive issue-free rounds.
  no hard cap   : there is no max round limit; the only non-natural exit is
                  stagnation (same issues overlapping across rounds) which
                  triggers an "ask the user" recommendation.
  subjects      : fixed subjects are constant per round; dynamic subjects must
                  differ across rounds (enforced by the used-subjects registry).

State shape (JSON):
  {
    "project": "/abs/path",
    "rounds": [ {round, subjects, dynamic_subjects, issues_found,
                 issues_fixed, smoke, clean} ],
    "streak": 0,
    "used_dynamic_subjects": [...],
    "stagnation_streak": 0,
    "last_issue_ids": [...]
  }

Exit codes:
  0  ok, continue
  2  error (e.g. duplicate dynamic subjects, fewer than 5, bad state)
  3  DONE — three consecutive issue-free rounds achieved
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIXED_SUBJECTS = [
    "correctness",      # code correctness incl. reference checks
    "comparison",       # version / logic comparison
    "standards",        # language / framework / project conventions
    "emoji",            # remove all emoji from code & docs
    "style",            # formatting / naming / consistency
    "smoke",            # smoke tests
]

MIN_DYNAMIC_SUBJECTS = 5

REQUIRED_STATE_KEYS = [
    "project", "rounds", "streak", "used_dynamic_subjects",
    "stagnation_streak", "last_issue_ids",
]


def die(msg: str) -> None:
    """Print an error to stderr and exit with code 2."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def new_state(project: str) -> dict:
    return {
        "project": project,
        "rounds": [],
        "streak": 0,
        "used_dynamic_subjects": [],
        "stagnation_streak": 0,
        "last_issue_ids": [],
    }


def load_state(arg: str, as_json: str | None) -> tuple[dict, str | None]:
    """Return (state, state_file). Prefers --state-json over --state."""
    if as_json is not None:
        try:
            state = json.loads(as_json)
        except json.JSONDecodeError as e:
            die(f"invalid --state-json: {e}")
        state_file = None
    elif arg:
        p = Path(arg)
        if not p.exists():
            die(f"state file not found: {p}")
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"state file is not valid JSON (corrupted?): {p}: {e}")
        state_file = str(p)
    else:
        # in-memory fallback: start fresh
        return new_state("<memory>"), None
    missing = [k for k in REQUIRED_STATE_KEYS if k not in state]
    if missing:
        die(f"state is missing required fields: {missing}")
    return state, state_file


def save_state(state: dict, state_file: str | None) -> None:
    if state_file:
        p = Path(state_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=True, indent=2),
                     encoding="utf-8")


def print_summary(state: dict, done: bool = False) -> None:
    n = len(state["rounds"])
    last = state["rounds"][-1] if state["rounds"] else None
    print(f"rounds: {n} | streak: {state['streak']} | "
          f"stagnation: {state['stagnation_streak']} | "
          f"done: {'YES' if done else 'no'}")
    if last:
        print(f"  last round #{last['round']}: "
              f"clean={last['clean']} issues={last['issues_found']} "
              f"fixed={last['issues_fixed']} smoke={last['smoke']}")
        print(f"  dynamic subjects: {', '.join(last['dynamic_subjects'])}")


def emit(state: dict, json_out: bool, done: bool) -> int:
    if json_out:
        print(json.dumps(state, ensure_ascii=True, indent=2))
    else:
        print_summary(state, done)
    return 3 if done else 0


def cmd_init(args) -> int:
    state = new_state(args.project)
    save_state(state, args.state)
    return emit(state, args.json, False)


def cmd_start_round(args) -> int:
    state, state_file = load_state(args.state, args.state_json)
    try:
        dynamic = json.loads(args.dynamic)
    except json.JSONDecodeError as e:
        die(f"invalid --dynamic JSON: {e}")
    if not isinstance(dynamic, list) or not all(
            isinstance(x, str) and x for x in dynamic):
        die("--dynamic must be a JSON array of non-empty strings")
    if len(dynamic) < MIN_DYNAMIC_SUBJECTS and not args.allow_fewer:
        die(f"need at least {MIN_DYNAMIC_SUBJECTS} dynamic subjects "
            f"(got {len(dynamic)}); pass --allow-fewer to override")

    used = set(state["used_dynamic_subjects"])
    dups = [d for d in dynamic if d in used]
    if dups:
        die(f"dynamic subjects already used in earlier rounds: "
            f"{dups}; they must differ across rounds")

    round_no = len(state["rounds"]) + 1
    state["rounds"].append({
        "round": round_no,
        "subjects": list(FIXED_SUBJECTS) + list(dynamic),
        "dynamic_subjects": list(dynamic),
        "issues_found": None,
        "issues_fixed": None,
        "smoke": None,
        "clean": None,
    })
    state["used_dynamic_subjects"].extend(dynamic)
    save_state(state, state_file)
    return emit(state, args.json, False)


def cmd_record(args) -> int:
    state, state_file = load_state(args.state, args.state_json)
    if not state["rounds"]:
        die("no round started yet; call start-round first")
    last = state["rounds"][-1]
    if last["issues_found"] is not None:
        die(f"round {last['round']} already recorded")

    if args.smoke not in ("pass", "fail", "skip"):
        die("--smoke must be pass|fail|skip")
    # A round is clean only when zero issues were found AND smoke did not
    # fail — a failing smoke test counts as an issue even if --issues is 0.
    clean = args.issues == 0 and args.smoke != "fail"
    last.update({
        "issues_found": args.issues,
        "issues_fixed": args.fixed,
        "smoke": args.smoke,
        "clean": clean,
    })
    state["streak"] = state["streak"] + 1 if clean else 0

    # Stagnation: overlap between this round's issue ids and the previous round's.
    if args.issue_ids:
        try:
            cur_ids = json.loads(args.issue_ids)
        except json.JSONDecodeError as e:
            die(f"invalid --issue-ids JSON: {e}")
        if not isinstance(cur_ids, list):
            die("--issue-ids must be a JSON array")
        prev_ids = set(state["last_issue_ids"])
        overlap = [i for i in cur_ids if i in prev_ids]
        state["stagnation_streak"] = state["stagnation_streak"] + 1 if overlap else 0
        state["last_issue_ids"] = cur_ids
        if state["stagnation_streak"] >= 2 and overlap:
            # keep stdout pure for --json consumers
            print("stagnation: same issues persist across two rounds — "
                  "recommend asking the user whether to continue (or stop)",
                  file=sys.stderr)
    else:
        state["last_issue_ids"] = []

    save_state(state, state_file)
    done = state["streak"] >= 3
    return emit(state, args.json, done)


def cmd_status(args) -> int:
    state, _ = load_state(args.state, args.state_json)
    return emit(state, args.json, state["streak"] >= 3)


def cmd_stagnation(args) -> int:
    """Pure overlap check between two issue-id lists (helper for agents)."""
    try:
        prev_ids = set(json.loads(args.prev_issues))
        cur_ids = set(json.loads(args.cur_issues))
    except json.JSONDecodeError as e:
        die(f"invalid issue JSON: {e}")
    overlap = sorted(prev_ids & cur_ids)
    result = {"overlap": overlap, "persisting": len(overlap) > 0}
    print(json.dumps(result, ensure_ascii=True, indent=2) if args.json
          else f"overlap: {len(overlap)} issue(s) persisting from previous round")
    return 1 if result["persisting"] else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Multi-round self-check state machine.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="create a fresh state")
    p_init.add_argument("--project", required=True)
    p_init.add_argument("--state", help="state file path (persists)")
    p_init.add_argument("--json", action="store_true")
    p_init.set_defaults(fn=cmd_init)

    p_start = sub.add_parser(
        "start-round", help="open a new round with dynamic subjects")
    p_start.add_argument("--dynamic", required=True,
                         help='JSON array of >=5 dynamic subject names')
    p_start.add_argument("--state", help="state file path")
    p_start.add_argument("--state-json", help="inline state JSON (no file)")
    p_start.add_argument("--allow-fewer", action="store_true")
    p_start.add_argument("--json", action="store_true")
    p_start.set_defaults(fn=cmd_start_round)

    p_rec = sub.add_parser("record", help="record the current round result")
    p_rec.add_argument("--state", help="state file path")
    p_rec.add_argument("--state-json", help="inline state JSON (no file)")
    p_rec.add_argument("--issues", type=int, required=True)
    p_rec.add_argument("--fixed", type=int, required=True)
    p_rec.add_argument("--smoke", required=True, choices=["pass", "fail", "skip"])
    p_rec.add_argument("--issue-ids",
                       help="JSON array of stable issue ids found this round")
    p_rec.add_argument("--json", action="store_true")
    p_rec.set_defaults(fn=cmd_record)

    p_st = sub.add_parser("status", help="print current state")
    p_st.add_argument("--state", help="state file path")
    p_st.add_argument("--state-json", help="inline state JSON (no file)")
    p_st.add_argument("--json", action="store_true")
    p_st.set_defaults(fn=cmd_status)

    p_sg = sub.add_parser("stagnation", help="pure overlap check of issue ids")
    p_sg.add_argument("--prev-issues", required=True, help="JSON array")
    p_sg.add_argument("--cur-issues", required=True, help="JSON array")
    p_sg.add_argument("--json", action="store_true")
    p_sg.set_defaults(fn=cmd_stagnation)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
