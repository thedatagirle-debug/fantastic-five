"""Shared data-loading and metric computation for the Fantastic Five dashboard.

All scoring logic lives here so the UI stays thin. Re-reads data/members.csv and
data/teams.csv (produced by build_dataset.py), so adding Round 4/5 images and
re-running the build is all that's needed to refresh the dashboard.
"""
import os
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CRITERIA = ["pitch", "rhythm", "diction", "feel_attitude", "o_performance"]
CRITERIA_LABELS = {
    "pitch": "Pitch", "rhythm": "Rhythm", "diction": "Diction",
    "feel_attitude": "Feel/Attitude", "o_performance": "Overall Perf.",
}
MY_TEAM = "GOLDEN RRR"


def load():
    members = pd.read_csv(os.path.join(DATA_DIR, "members.csv"))
    teams = pd.read_csv(os.path.join(DATA_DIR, "teams.csv"))
    for c in ["grand_total", "team_total", "penalty"] + \
             [f"avg_{x}" for x in CRITERIA] + \
             [f"j1_{x}" for x in CRITERIA] + [f"j2_{x}" for x in CRITERIA] + \
             ["j1_total", "j2_total"]:
        if c in members.columns:
            members[c] = pd.to_numeric(members[c], errors="coerce")
    teams["team_total"] = pd.to_numeric(teams["team_total"], errors="coerce")
    teams["round"] = pd.to_numeric(teams["round"], errors="coerce").astype("Int64")
    members["round"] = pd.to_numeric(members["round"], errors="coerce").astype("Int64")
    return members, teams


def team_standings(teams):
    """One row per team: per-round totals, cumulative, average, trajectory slope."""
    pivot = teams.pivot_table(index="team", columns="round", values="team_total", aggfunc="first")
    pivot.columns = [f"R{int(c)}" for c in pivot.columns]
    out = pivot.copy()
    out["rounds_played"] = pivot.notna().sum(axis=1)
    out["total"] = pivot.sum(axis=1, min_count=1)
    out["average"] = pivot.mean(axis=1)
    out["best_round"] = pivot.max(axis=1)
    out["last"] = pivot.apply(lambda r: r.dropna().iloc[-1] if r.notna().any() else np.nan, axis=1)
    out["first"] = pivot.apply(lambda r: r.dropna().iloc[0] if r.notna().any() else np.nan, axis=1)
    out["momentum"] = out["last"] - out["first"]            # raw improvement R1 -> latest
    out["trend"] = teams.groupby("team").apply(_slope, include_groups=False)
    out = out.sort_values("average", ascending=False)
    out["rank"] = range(1, len(out) + 1)
    # captain lookup
    cap = teams.sort_values("round").groupby("team")["captain"].last()
    out["captain"] = cap
    return out.reset_index()


def _slope(g):
    g = g.dropna(subset=["team_total"])
    if len(g) < 2:
        return 0.0
    x = g["round"].astype(float).values
    y = g["team_total"].astype(float).values
    return float(np.polyfit(x, y, 1)[0])


def member_standings(members):
    """One row per member (across rounds): average + cumulative grand_total, trend."""
    g = members.groupby(["team", "member"], as_index=False).agg(
        rounds=("round", "nunique"),
        avg_grand=("grand_total", "mean"),
        total_grand=("grand_total", "sum"),
        best_grand=("grand_total", "max"),
    )
    # per-criterion averages
    for c in CRITERIA:
        col = f"avg_{c}"
        if col in members.columns:
            cm = members.groupby(["team", "member"])[col].mean().reset_index()
            g = g.merge(cm, on=["team", "member"], how="left")
    # trend (slope of grand_total across rounds)
    tr = members.groupby(["team", "member"]).apply(
        lambda d: _member_slope(d), include_groups=False).rename("trend").reset_index()
    g = g.merge(tr, on=["team", "member"], how="left")
    g["avg_grand"] = g["avg_grand"].round(2)
    return g.sort_values("avg_grand", ascending=False)


def _member_slope(d):
    d = d.dropna(subset=["grand_total"])
    if len(d) < 2:
        return 0.0
    return float(np.polyfit(d["round"].astype(float), d["grand_total"].astype(float), 1)[0])


def top_per_team(members):
    ms = member_standings(members)
    idx = ms.groupby("team")["avg_grand"].idxmax()
    return ms.loc[idx].sort_values("avg_grand", ascending=False)


def criteria_profile(members, team=None):
    """Average per-criterion score, optionally filtered to one team."""
    df = members if team is None else members[members["team"] == team]
    return {c: df[f"avg_{c}"].mean() for c in CRITERIA if f"avg_{c}" in df.columns}


def team_criteria_matrix(members):
    """teams x criteria average-score matrix + each team's rank per criterion (1=best)."""
    rows = {}
    for c in CRITERIA:
        col = f"avg_{c}"
        if col in members.columns:
            rows[c] = members.groupby("team")[col].mean()
    mat = pd.DataFrame(rows)
    mat.columns = [CRITERIA_LABELS[c] for c in mat.columns]
    ranks = mat.rank(ascending=False, method="min").astype(int)
    ranks.columns = [f"{c} rank" for c in mat.columns]
    return mat, ranks


def matchup(members, team_a, team_b):
    """Per-criterion comparison of two teams + an auto game plan for team_a vs team_b."""
    a = criteria_profile(members[members["team"] == team_a])
    b = criteria_profile(members[members["team"] == team_b])
    rows = []
    for k in a:
        diff = a[k] - b[k]
        rows.append({"criterion": CRITERIA_LABELS[k], "key": k,
                     team_a: round(a[k], 2), team_b: round(b[k], 2),
                     "diff": round(diff, 2),
                     "verdict": "you lead" if diff > 0.03 else ("they lead" if diff < -0.03 else "level")})
    df = pd.DataFrame(rows).sort_values("diff")
    their_edge = df[df["verdict"] == "they lead"]      # close these to beat them
    your_edge = df[df["verdict"] == "you lead"]         # lean into these
    return df, their_edge, your_edge


def _seed_order(n):
    """Standard single-elimination seeding order for a power-of-2 bracket."""
    order = [1]
    while len(order) < n:
        m = len(order) * 2
        order = [x for s in order for x in (s, m + 1 - s)]
    return order


def project_bracket(standings, members, n_seeds, metric, my_team):
    """Seed the top n_seeds teams, predict each match by score, and trace my_team's
    road to the title (assuming they win each round). Returns (seeds_df, rounds, my_path)."""
    seeds_df = standings.sort_values(metric, ascending=False).head(n_seeds).reset_index(drop=True)
    seeds_df["seed"] = range(1, len(seeds_df) + 1)
    n = len(seeds_df)
    score = dict(zip(seeds_df["seed"], seeds_df[metric]))
    team = dict(zip(seeds_df["seed"], seeds_df["team"]))
    order = _seed_order(n)

    def rname(num_matches):
        return {1: "🏅 Final", 2: "🥈 Semi-final", 4: "Quarter-final"}.get(
            num_matches, f"Round of {num_matches * 2}")

    my_seed = next((s for s, t in team.items() if t == my_team), None)
    rounds, my_path = [], []
    nodes = order[:]
    while len(nodes) > 1:
        matches, newnodes = [], []
        for i in range(0, len(nodes), 2):
            a, b = nodes[i], nodes[i + 1]
            if my_seed in (a, b):                 # my_team is forced to advance
                w = my_seed
                opp = b if a == my_seed else a
                my_path.append({"round": rname(len(nodes) // 2),
                                "opponent": team[opp], "opp_seed": opp})
            else:                                  # everyone else advances by score
                w = a if score[a] >= score[b] else b
            matches.append({"a": team[a], "a_seed": a, "b": team[b], "b_seed": b, "winner": team[w]})
            newnodes.append(w)
        rounds.append({"name": rname(len(nodes) // 2), "matches": matches})
        nodes = newnodes
    return seeds_df, rounds, my_path


def member_criteria(members):
    """Per (team, member) average of each criterion across the rounds they performed,
    plus rounds played (handles substitutes who miss rounds)."""
    cols = [f"avg_{c}" for c in CRITERIA if f"avg_{c}" in members.columns]
    g = members.groupby(["team", "member"]).agg(
        rounds=("round", "nunique"),
        rounds_list=("round", lambda s: sorted(int(x) for x in s.dropna().unique())),
        avg_grand=("grand_total", "mean"),
        **{c: (c, "mean") for c in cols},
    ).reset_index()
    return g


def weakest_criterion(row):
    """Given a member_criteria row, return (criterion_key, label, score) of their lowest."""
    vals = {c: row[f"avg_{c}"] for c in CRITERIA if f"avg_{c}" in row.index and pd.notna(row.get(f"avg_{c}"))}
    if not vals:
        return None, None, None
    k = min(vals, key=vals.get)
    return k, CRITERIA_LABELS[k], vals[k]


# keyword -> criterion mapping for decoding Tanglish judge feedback
_FB_CRIT = {
    "pitch": "pitch", "sruthi": "pitch", "shruthi": "pitch", "apaswaram": "pitch",
    "off pitch": "pitch", "scale": "pitch",
    "rhythm": "rhythm", "beat": "rhythm", "timing": "rhythm", "tempo": "rhythm", "thaalam": "rhythm",
    "diction": "diction", "pronunciation": "diction", "pronounce": "diction", "words": "diction",
    "lyrics": "diction", "ucharippu": "diction",
    "dynamics": "feel_attitude", "feel": "feel_attitude", "attitude": "feel_attitude",
    "energy": "feel_attitude", "emotion": "feel_attitude", "expression": "feel_attitude",
    "landing": "o_performance", "breath": "o_performance", "humming": "o_performance",
    "modulation": "o_performance", "performance": "o_performance", "stage": "o_performance",
}
_PRAISE = ["superb", "beautiful", "excellent", "wonderful", "great", "lovely", "nice",
           "good singing", "well", "perfect", "amazing", "neat", "clarity", "pure rendition"]


def feedback_insights(text):
    """Heuristically decode a Tanglish judge-feedback blob into:
    {praise: [...], suggestion: 'text', focus: [criterion labels mentioned to improve]}."""
    text = str(text or "")
    low = text.lower()
    praise = sorted({w for w in _PRAISE if w in low})
    suggestion = ""
    for marker in ["suggestion:", "suggestion ", "improve", "next time", "concentrate", "check "]:
        i = low.find(marker)
        if i != -1:
            suggestion = text[i:].strip()
            break
    # criteria flagged anywhere in the feedback
    focus = []
    for kw, crit in _FB_CRIT.items():
        if kw in low and CRITERIA_LABELS[crit] not in focus:
            focus.append(CRITERIA_LABELS[crit])
    return {"praise": praise, "suggestion": suggestion[:400], "focus": focus}


def load_insights():
    """LLM-decoded judge feedback: dict[(team, round, member)] -> {positives, negatives, focus}.
    Produced offline by analyze_feedback.py; empty dict if not present (app degrades gracefully)."""
    import json
    path = os.path.join(DATA_DIR, "insights.json")
    if not os.path.exists(path):
        return {}
    out = {}
    for it in json.load(open(path)):
        try:
            out[(it["team"], int(it["round"]), it["member"])] = it
        except (KeyError, ValueError, TypeError):
            continue
    return out


def member_insight(insights, team, member, round=None):
    """Aggregate decoded positives/negatives/focus for a singer across rounds
    (or a single round if given), de-duplicated in first-seen order."""
    pos, neg, foc = [], [], []
    for (t, r, m), it in insights.items():
        if t != team or m != member:
            continue
        if round is not None and r != round:
            continue
        for p in it.get("positives", []):
            if p not in pos:
                pos.append(p)
        for n in it.get("negatives", []):
            if n not in neg:
                neg.append(n)
        for f in it.get("focus", []):
            if f not in foc:
                foc.append(f)
    return {"positives": pos, "negatives": neg, "focus": foc}


def _phrase_to_criterion(phrase):
    low = (phrase or "").lower()
    for kw, crit in _FB_CRIT.items():
        if kw in low:
            return CRITERIA_LABELS[crit]
    return None


# specific recurring issue themes (beyond the 5 criteria) to track across rounds.
# Keywords are matched against the decoded negatives — keep them broad enough to
# catch phrasing variants (e.g. "2nd join", "self-join", "utilize options" all = join/duet).
# Each theme is a human reasoning label -> a list of REASONING PHRASES (concept fragments)
# that mean the same thing. A round's feedback matches the theme if any phrase appears in it.
# Phrases (not bare words) keep matching precise and the output reads like an insight.
_THEMES = {
    "should use the 2nd join (duet) option": [
        "2nd join", "second join", "self join", "self-join", "single join", "double join",
        "duet", "split the lyric", "shrink the song", "use the option", "utilize the option",
        "didn't use 2nd join", "did not use 2nd join", "join option"],
    "pitch goes flat / off sruthi": [
        "pitch flat", "goes flat", "flat in", "slightly flat", "off pitch", "off-key",
        "sruthi", "apaswaram", "pitch differ", "scale differ", "pitch issue", "pitch waver",
        "pitch slip", "pitch problem"],
    "feel / attitude / dynamics lacking": [
        "more feel", "feel missing", "add feel", "lacks feel", "attitude", "more dynamics",
        "add dynamics", "dynamics missing", "more energy", "expression", "emotion"],
    "landings cut short / not sustained": ["landing"],
    "should sustain notes longer": ["sustain"],
    "strain on high notes": ["high note"],
    "voice strain / crack": ["voice strain", "strained", "voice crack", "compress"],
    "breath control on long lines": ["breath"],
    "humming needs work": ["humming"],
    "fillers / sangathi to add or clean": ["filler", "sangathi"],
    "diction / pronunciation / word clarity": [
        "diction", "pronunc", "word clarity", "clarity of words", "words not clear",
        "unclear words", "lyric clarity"],
    "timing / rhythm lag": ["timing", "tempo", "rushed", "off beat", "rhythm lag", "behind beat"],
    "voice modulation": ["modulation"],
    "voice / song settings need fixing": ["voice setting", "song setting", "settings", "mic setting"],
    "missing / uncovered portions of the song": [
        "missing", "missed portion", "not covered", "skipped", "left out"],
    "weak in a specific section (pallavi/charanam)": ["pallavi", "charanam", "anupallavi"],
    "syncing with the backing track": ["with the track", "track la", "backing track",
                                       "track sync", "along the track"],
}


def recurring(insights, team, member):
    """Detect criteria/themes that repeat across a singer's rounds.
    Returns counts out of rounds_seen for praise-criteria, issue-criteria and issue-themes
    (only those appearing in >= 2 rounds)."""
    from collections import Counter
    rounds = {r: it for (t, r, m), it in insights.items() if t == team and m == member}
    n = len(rounds)
    praise_c, issue_c, theme_c = Counter(), Counter(), Counter()
    for it in rounds.values():
        for f in set(it.get("focus", [])):                       # standardized weakness criteria
            issue_c[f] += 1
        pc = {c for p in it.get("positives", []) if (c := _phrase_to_criterion(p))}
        for c in pc:                                             # praise mapped to criteria
            praise_c[c] += 1
        negtext = " ".join(it.get("negatives", [])).lower()
        for theme, kws in _THEMES.items():
            if any(k in negtext for k in kws):
                theme_c[theme] += 1
    rec = lambda c: sorted([(k, v) for k, v in c.items() if v >= 2], key=lambda x: -x[1])
    return {"rounds": n, "praise_criteria": rec(praise_c),
            "issue_criteria": rec(issue_c), "issue_themes": rec(theme_c)}


def potential_table(teams, members):
    """Potential = where a team is trending + how high its ceiling is + member depth.
    Blends current average, upward trajectory, best-round ceiling and roster balance."""
    st = team_standings(teams).set_index("team")
    ms = member_standings(members)
    # roster balance: lower spread between best & weakest member = more depth
    bal = ms.groupby("team")["avg_grand"].agg(["mean", "min", "max"])
    bal["spread"] = bal["max"] - bal["min"]
    rows = []
    for t in st.index:
        avg = st.loc[t, "average"]
        trend = st.loc[t, "trend"]
        ceiling = st.loc[t, "best_round"]
        spread = bal.loc[t, "spread"] if t in bal.index else np.nan
        rows.append({"team": t, "avg": avg, "trend": trend,
                     "ceiling": ceiling, "depth_spread": spread})
    p = pd.DataFrame(rows)
    # normalize each component 0-1 then weight
    def nz(s, invert=False):
        s = (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else s * 0
        return 1 - s if invert else s
    p["potential_score"] = (
        0.40 * nz(p["avg"]) +
        0.30 * nz(p["trend"]) +
        0.15 * nz(p["ceiling"]) +
        0.15 * nz(p["depth_spread"], invert=True)
    ).round(3)
    return p.sort_values("potential_score", ascending=False).reset_index(drop=True)
