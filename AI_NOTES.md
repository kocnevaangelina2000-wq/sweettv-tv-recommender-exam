# AI_NOTES — how an AI assistant was used

| item | value |
|---|---|
| tool | Claude Code (Anthropic's CLI agent), version 2.1.309 |
| model | Claude Opus 5.5 (`claude-opus-5-5`); all assistant turns in the transcript report this model |
| session id | `d3e92eca-8fdc-404d-a062-5f4671e3db6b` (one session, 2026-10-22 19:34 UTC → 2026-10-24, with one context compaction) |
| transcript | `~/.claude/projects/-Users-avkochneva-Desktop-exam/d3e92eca-8fdc-404d-a062-5f4671e3db6b.jsonl` (local, not in the repo) |

## Counts
Counted from the transcript file with a short Python script on 2026-10-24, before the step-6 commit. The calls that followed (building the report, committing, pushing) are not included.

| kind | count |
|---|---|
| user messages: pasted step briefs | 10 |
| user messages: typed | 5 |
| background-task notifications delivered to the model | 16 |
| context-compaction summaries | 1 |
| tool calls in total | 235 |
| tool calls by tool | Bash 177 · Write 29 · Read 11 · Edit 9 · ToolSearch 3 · Monitor 2 · WebSearch 2 · TaskStop 1 · WebFetch 1 |

## Division of work
- **The user** wrote every step brief, set the rules: one commit per step, BUGLOG / DESIGN / RESULTS, no faked numbers, select on fold A, and no Kaggle submissions by the assistant. The user made every Kaggle submission and reported the scores, chose the final file (s8, best private score, per the instructor's rule), and asked for s9 and s10 after seeing the leaderboard.
- **The assistant** wrote the code in `src/` and `tests/`, ran every experiment, and wrote `RESULTS.md`, `DESIGN.md`, `BUGLOG.md`, `README.md` and the report draft. It never submitted to Kaggle.
- **Placeholders for the user:** "Discussion in my words" and "Personal verification" in the report, plus the Kaggle screenshot. A hand-check pack for one user (`analysis/hand_check_user.md`) was prepared so that the user can verify the join, screen time and AP@5 by hand.

## Files touched
- Git history at the time of writing: 12 commits touching 81 distinct paths: `src/` 26, `logs/` 32, `submissions/` 12, `analysis/` 5, `tests/` 1, plus the docs.
- Step 6 adds: `README.md`, `AI_NOTES.md`, `requirements.txt`, `report/` (report.md, build_pdf.py, report.html, report.pdf), `analysis/refs/` (6 raw records + index), `screenshots/README.md`, `src/examples.py` and `logs/examples.*`.
- Outside the repo, the assistant also installed `markdown` 3.7 into a scratch directory (for the PDF build only) and the GitHub CLI via Homebrew.

## Errors made by the assistant (all logged)
- B25: wrong-row indexing in a hybrid component.
- B28: a diverged Poisson model was committed and later fixed.
- B24: thread setting applied too late.
- B34: the catboost install downgraded numpy.
- B41: a bug in a validation script.

Several report claims were corrected before commit after being checked against the logs; see the step-6 commit.

## Before publishing
Raw competition rows were removed from every commit before the first push (DESIGN D70): the two hand-check CSVs and 11 raw lines in `logs/stats.log`. The commit hashes reported in earlier step messages refer to the pre-rewrite history, which exists only in the local branch `backup/pre-public-scrub`.
