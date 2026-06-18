"""
Consolidate all data/raw/batch_*.json scorecards into clean, analysis-ready tables.

Outputs (written to data/):
  - members.csv : one row per (team, round, member) with both judges' sub-scores,
                  totals, grand_total, compliance flags, penalty, feedback.
  - teams.csv   : one row per (team, round) with team_total + derived ranks.
  - clean.json  : the full nested structure (deduped) for reference.

Re-run this whenever new round images are extracted into data/raw/.
"""
import json, glob, os, re
from difflib import SequenceMatcher
import pandas as pd

RAW_DIR = "data/raw"
OUT_DIR = "data"

CRITERIA = ["pitch", "rhythm", "diction", "feel_attitude", "o_performance"]


def norm_team(t):
    return (t or "").strip().upper()


def _norm_name(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def content_sig(r):
    """Signature of a card by team + its members' grand totals (normalized to 1 decimal).
    Excludes team_total (varies pre/post penalty) and ignores 95 vs 95.0 formatting, so
    the same physical card photographed twice / read by two agents dedupes reliably."""
    def g(m):
        try:
            return round(float(m.get("grand_total")), 1)
        except (TypeError, ValueError):
            return None
    gts = tuple(sorted((x for x in (g(m) for m in r.get("members", [])) if x is not None)))
    return (norm_team(r.get("team")), gts)


def load_records():
    """Load all cards, dropping exact-duplicate screenshots (same team + totals)."""
    records, seen_sig = [], set()
    for f in sorted(glob.glob(os.path.join(RAW_DIR, "batch_*.json"))):
        d = json.load(open(f))
        for r in d.get("records", []):
            sig = content_sig(r)
            if sig in seen_sig:
                continue
            seen_sig.add(sig)
            records.append(r)
    return records


def canonicalize_names(records):
    """Within each team, merge member-name variants that are identical up to
    whitespace/punctuation/case (e.g. 'Toxic Freakin Raya' vs 'Toxic Freakin_Raya').
    Genuinely different names (real substitutes) are left untouched."""
    from collections import defaultdict, Counter
    variants = defaultdict(Counter)  # (team, normkey) -> Counter of raw spellings
    for r in records:
        t = norm_team(r.get("team"))
        for m in r.get("members", []):
            nm = (m.get("name") or "").strip()
            if nm:
                variants[(t, _norm_name(nm))][nm] += 1
    canon = {k: c.most_common(1)[0][0] for k, c in variants.items()}
    merged = 0
    for r in records:
        t = norm_team(r.get("team"))
        for m in r.get("members", []):
            nm = (m.get("name") or "").strip()
            c = canon.get((t, _norm_name(nm)))
            if c and c != nm:
                m["name"] = c
                merged += 1
    return records


def fix_rounds(records):
    """Apply competition rule: within a team, earliest year = Round 1, next = Round 2,
    etc. Years never go backward. Ties on year keep the stored round as tiebreaker."""
    from collections import defaultdict
    by_team = defaultdict(list)
    for r in records:
        by_team[norm_team(r.get("team"))].append(r)
    for team, cards in by_team.items():
        def yr(r):
            try:
                return int(str(r.get("year")))
            except (TypeError, ValueError):
                return 9999
        cards.sort(key=lambda r: (yr(r), r.get("round") or 99))
        for i, r in enumerate(cards, start=1):
            stored = r.get("round")
            if stored != i:
                r["_round_fixed_from"] = stored
            r["round"] = i
    return records


def pull_penalty(member):
    """Detect a late-submission/other deduction from any extra field or feedback text."""
    for fld in ("deduction", "penalty", "penalty_note", "note"):
        v = member.get(fld)
        if v is None:
            continue
        m = re.search(r"-\s?(\d+(?:\.\d+)?)", str(v))
        if m:
            return float(m.group(1))
        if isinstance(v, (int, float)) and v:
            return abs(float(v))
    fb = (member.get("feedback") or "")
    m = re.search(r"late submission\s*-\s*(\d+)", fb, re.I)
    if m:
        return float(m.group(1))
    return 0.0


def judge_map(member):
    out = {}
    for j in member.get("judges", []):
        out[(j.get("judge") or "").upper()] = j
    return out


def main():
    records = fix_rounds(canonicalize_names(load_records()))
    member_rows, team_rows = [], []

    for r in records:
        team = norm_team(r.get("team"))
        rnd = r.get("round")
        # header line 2 = the team CAPTAIN's name (NOT a theme)
        captain = (r.get("theme") or "").strip()
        year = r.get("year")
        image = r.get("image")
        members = r.get("members", [])
        # identify which member row is the captain (best fuzzy match to header name)
        cap_norm = _norm_name(captain)
        cap_idx = None
        if cap_norm and members:
            scores = [SequenceMatcher(None, cap_norm, _norm_name(m.get("name"))).ratio()
                      for m in members]
            best = max(range(len(members)), key=lambda i: scores[i])
            if scores[best] >= 0.5:
                cap_idx = best
        team_rows.append({
            "team": team, "round": rnd, "captain": captain, "year": year,
            "team_total": r.get("team_total"), "image": image,
        })
        for mi, m in enumerate(members):
            jm = judge_map(m)
            row = {
                "team": team, "round": rnd, "captain": captain, "year": year,
                "image": image, "member": (m.get("name") or "").strip(),
                "is_captain": (mi == cap_idx),
            }
            comp = m.get("compliance") or {}
            for c in ("year", "slogan", "dp_check", "tag_check"):
                row[f"comp_{c}"] = str(comp.get(c, "")).upper()
            for jlabel in ("J1", "J2"):
                j = jm.get(jlabel, {})
                for crit in CRITERIA:
                    row[f"{jlabel.lower()}_{crit}"] = j.get(crit)
                row[f"{jlabel.lower()}_total"] = j.get("total")
            # average per-criterion across the two judges (for radar/strength profile)
            for crit in CRITERIA:
                vals = [row.get(f"j1_{crit}"), row.get(f"j2_{crit}")]
                vals = [v for v in vals if isinstance(v, (int, float))]
                row[f"avg_{crit}"] = round(sum(vals) / len(vals), 2) if vals else None
            row["grand_total"] = m.get("grand_total")
            row["penalty"] = pull_penalty(m)
            row["feedback"] = m.get("feedback") or ""
            member_rows.append(row)

    members = pd.DataFrame(member_rows)
    teams = pd.DataFrame(team_rows)

    # Derived: per-round team rank (higher team_total = better)
    teams["round_rank"] = teams.groupby("round")["team_total"].rank(
        ascending=False, method="min").astype("Int64")

    members.to_csv(os.path.join(OUT_DIR, "members.csv"), index=False)
    teams.to_csv(os.path.join(OUT_DIR, "teams.csv"), index=False)
    json.dump(records, open(os.path.join(OUT_DIR, "clean.json"), "w"),
              indent=2, ensure_ascii=False)

    print(f"members.csv : {len(members)} rows")
    print(f"teams.csv   : {len(teams)} rows  ({teams['team'].nunique()} teams, rounds {sorted(teams['round'].dropna().unique())})")
    print(f"members with penalty: {(members['penalty']>0).sum()}")
    print(f"compliance != YES   : {((members.filter(like='comp_')!='YES').any(axis=1)).sum()} members")


if __name__ == "__main__":
    main()
