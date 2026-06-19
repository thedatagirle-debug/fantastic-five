"""Generate STRATEGY.md for Golden RRR from the current data (all rounds).
Re-run after each data refresh:  python generate_strategy.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))
import metrics as M

members, teams = M.load()
ins = M.load_insights()
st = M.team_standings(teams).sort_values("average", ascending=False).reset_index(drop=True)
st["pos"] = range(1, len(st) + 1)
rounds = sorted(int(x) for x in teams["round"].dropna().unique())
my = st[st["team"] == M.MY_TEAM].iloc[0]
pos = int(my["pos"])
leader = st.iloc[0]
ahead = st[st["pos"] < pos]["team"].tolist()
cutline = st.iloc[5]  # team on the #6 line (top-ish reference)

mine = M.criteria_profile(members[members["team"] == M.MY_TEAM])
riv = M.criteria_profile(members[members["team"].isin(ahead)]) if ahead else mine
gaps = sorted(((M.CRITERIA_LABELS[k], mine[k] - riv[k]) for k in mine), key=lambda x: x[1])

ms = M.member_standings(members)
gm = ms[ms["team"] == M.MY_TEAM].sort_values("avg_grand")

L = []
L.append(f"# Golden RRR — Path to the Top 🎯\n")
L.append(f"*Captain: {my['captain']}. Based on Rounds {rounds[0]}–{rounds[-1]} "
         f"({len(teams)} cards, {teams['team'].nunique()} teams). Ranked by average score/round. "
         f"Auto-generated — re-run `generate_strategy.py` after each update.*\n")

L.append("## Where you stand")
L.append(f"- **Rank #{pos} of {len(st)}**, average **{my['average']:.1f}**/round.")
L.append(f"- Leader: **{leader['team']}** ({leader['average']:.1f}). Gap to #1: "
         f"**{leader['average'] - my['average']:.1f}**. The team one place above you "
         f"(**{st.iloc[pos-2]['team']}**) is only **{st.iloc[pos-2]['average'] - my['average']:.1f}** ahead.")
L.append(f"- Momentum R{rounds[0]}→R{rounds[-1]}: **{my['momentum']:+.1f}** (trend {my['trend']:+.2f}/round).\n")

L.append("## The levers that matter most (per-criterion gap vs the teams above you)")
L.append("| Criterion | Golden RRR | Teams above | Gap |")
L.append("|---|---|---|---|")
for label, gap in sorted(((M.CRITERIA_LABELS[k], mine[k]-riv[k]) for k in mine), key=lambda x: x[1]):
    k = next(kk for kk in mine if M.CRITERIA_LABELS[kk] == label)
    tag = " ← biggest gap" if (label, gap) == (gaps[0][0], gaps[0][1]) else ""
    L.append(f"| {label} | {mine[k]:.2f} | {riv[k]:.2f} | {gap:+.2f}{tag} |")
worst = gaps[0]
L.append(f"\n**{worst[0]} is where you lose the race ({worst[1]:+.2f}).** Closing it is the cheapest "
         f"points on the board.\n")

L.append("## Your roster — recurring issues (the patterns judges keep flagging)")
L.append("| Singer | Avg | Best | Trend | Recurring issues (rounds flagged) |")
L.append("|---|---|---|---|---|")
for _, r in gm.iterrows():
    rec = M.recurring(ins, M.MY_TEAM, r["member"])
    themes = "; ".join(f"{t} ({v}×)" for t, v in rec["issue_themes"][:3]) or "—"
    L.append(f"| {r['member']} | {r['avg_grand']:.1f} | {r['best_grand']:.1f} | "
             f"{r['trend']:+.2f} | {themes} |")

# competition-wide recurring issues
crdf, elig = M.competition_recurring(ins, members)
L.append(f"\n## What the whole field struggles with ({elig} multi-round singers)")
for _, r in crdf.head(6).iterrows():
    L.append(f"- **{r['theme']}** — {int(r['singers'])} singers ({int(r['share_%'])}%)")
L.append("\n*Fixing an issue most rivals also have = where Golden RRR separates from the pack.*\n")

L.append("## Rival intel")
for rt in ahead[:5]:
    prof = M.criteria_profile(members[members["team"] == rt])
    best_k = max(prof, key=prof.get)
    trow = st[st["team"] == rt].iloc[0]
    L.append(f"- **{rt}** (avg {trow['average']:.1f}, trend {trow['trend']:+.2f}) — strongest at "
             f"**{M.CRITERIA_LABELS[best_k]}** ({prof[best_k]:.2f}).")

L.append("\n## Game plan")
L.append(f"1. **Drill {worst[0]}** — your #1 gap vs the teams above.")
L.append(f"2. **Coach the weakest links:** {gm.iloc[0]['member']} ({gm.iloc[0]['avg_grand']:.1f}) and "
         f"{gm.iloc[1]['member']} ({gm.iloc[1]['avg_grand']:.1f}).")
L.append("3. **Fix the recurring techniques** judges keep repeating (see roster table) — esp. landings "
         "and using the 2nd-join / duet option.")
L.append("4. **Lean into your edges** (Diction, Overall Performance) in song selection.")
L.append(f"5. **Target the beatable top team** and defend against the fast risers below you.\n")
L.append("*Live, interactive version: the 🎯 Golden RRR War Room and 🥊 Beat a Team tabs in the dashboard.*")

open("STRATEGY.md", "w").write("\n".join(L) + "\n")
print("STRATEGY.md regenerated for rounds", rounds)
