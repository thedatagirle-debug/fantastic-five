# 🎤 Fantastic Five — Competition Dashboard

Team & individual results, top performers, highest-potential teams, and a **Golden RRR strategy war room** — built from 64 scorecard images of the Fantastic Five singing competition.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app/dashboard.py
```
Open http://localhost:8501.

## Refresh data (when Round 4 / 5 images arrive)
1. Drop the new images into `Images/`.
2. Re-extract them into `data/raw/batch_*.json` (same JSON schema as existing batches).
3. Rebuild the clean tables and the whole dashboard updates automatically:
   ```bash
   python build_dataset.py
   ```
The dashboard reads `data/members.csv` and `data/teams.csv`, derives rounds from the
year rule (earliest year = Round 1), dedupes duplicate screenshots, and adapts to any
number of rounds. Elimination cut-offs (QF/SF/Final) are adjustable in the sidebar.

## Deploy publicly (Streamlit Community Cloud — free)
1. Push this folder to a GitHub repo.
2. Go to https://share.streamlit.io → **New app** → pick the repo.
3. Main file path: `app/dashboard.py`. Deploy. You get a public `*.streamlit.app` URL.

> Note: a public app exposes member names, scores and judge feedback to anyone with the
> link. If you ever want to restrict it, set `app_password = "..."` in
> `.streamlit/secrets.toml` (or the Streamlit Cloud "Secrets" box) and the built-in
> password gate activates — no code change needed.

## Layout
```
build_dataset.py     # image-JSON -> clean members.csv / teams.csv (with audit rules)
app/
  dashboard.py       # Streamlit UI (6 tabs)
  metrics.py         # all scoring / ranking / potential logic
data/
  raw/batch_*.json   # per-image extracted scorecards
  members.csv        # one row per (team, round, member)
  teams.csv          # one row per (team, round)
STRATEGY.md          # Golden RRR competitive analysis
```

## Dashboard tabs
- **🏆 Standings** — ranked table with projected elimination stages + per-round trend chart.
- **🎤 Teams** — per-team members, strength radar, round-by-round feedback.
- **👤 Individuals** — top performer of each team + full searchable ranking.
- **🎯 Golden RRR War Room** — gaps vs teams above, rival intel, per-singer improvement focus, judge suggestions.
- **🥊 Beat a Team** — pick any rival: per-criterion matchup, their edge to neutralise, your edge to lean into, **their threat singers with decoded judge feedback**, auto game plan + field-wide criterion ranks.
- **⚠️ Data notes** — provenance, audit rules, substitutes, known issues, CSV downloads.
