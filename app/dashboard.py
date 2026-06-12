"""
Fantastic Five — Competition Dashboard
Run:  streamlit run app/dashboard.py
Data: reads data/members.csv & data/teams.csv (rebuild with build_dataset.py to refresh).
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

import metrics as M

st.set_page_config(page_title="Fantastic Five Dashboard", page_icon="🎤", layout="wide")

# ----------------------------------------------------------------------------- auth (privacy)
def gate():
    """Optional password gate. Set a password in .streamlit/secrets.toml as
    app_password = "..."  — if unset, the app is open (fine for local use)."""
    try:
        pw = st.secrets.get("app_password", None)
    except Exception:
        pw = None  # no secrets.toml at all -> app is open (public)
    if not pw:
        return True
    if st.session_state.get("authed"):
        return True
    st.title("🎤 Fantastic Five")
    entered = st.text_input("Enter access password", type="password")
    if entered == pw:
        st.session_state["authed"] = True
        st.rerun()
    elif entered:
        st.error("Incorrect password")
    st.stop()

gate()

members, teams = M.load()
INSIGHTS = M.load_insights()        # LLM-decoded positives/negatives per singer-round
standings = M.team_standings(teams)
round_cols = [c for c in standings.columns if c.startswith("R") and c[1:].isdigit()]
all_rounds = sorted(int(c[1:]) for c in round_cols)

# ----------------------------------------------------------------------------- sidebar
st.sidebar.title("🎤 Fantastic Five")
st.sidebar.caption(f"{teams['team'].nunique()} teams · rounds {all_rounds} · {len(members)} performances")
st.sidebar.markdown("### Elimination cut-offs")
qf = st.sidebar.slider("→ Quarter-finals (teams)", 8, 21, 13)
sf = st.sidebar.slider("→ Semi-finals (teams)", 4, qf, 8)
fin = st.sidebar.slider("→ Final (teams)", 2, sf, 5)
rank_metric = st.sidebar.radio("Rank teams by", ["average", "total"],
                               format_func=lambda x: "Average / round (fair when rounds differ)"
                               if x == "average" else "Cumulative total")
st.sidebar.info("Add Round 4/5 images → run `build_dataset.py` → refresh. The whole dashboard updates automatically.")

st.title("🎤 Fantastic Five — Results Dashboard")

tabs = st.tabs(["🏆 Standings", "🎤 Teams", "👤 Individuals",
                "🎯 Golden RRR War Room", "🥊 Beat a Team", "⚠️ Data notes"])

# ============================================================================= STANDINGS
with tabs[0]:
    s = standings.sort_values(rank_metric, ascending=False).reset_index(drop=True)
    s["pos"] = range(1, len(s) + 1)

    def stage(pos):
        if pos <= fin: return "🏅 Final"
        if pos <= sf:  return "🥈 Semi-final"
        if pos <= qf:  return "🎫 Quarter-final"
        return "❌ Out"
    s["projected_stage"] = s["pos"].apply(stage)

    c1, c2, c3 = st.columns(3)
    c1.metric("Teams", len(s))
    golden_pos = int(s.loc[s["team"] == M.MY_TEAM, "pos"].iloc[0]) if (s["team"] == M.MY_TEAM).any() else None
    c2.metric("Golden RRR rank", f"#{golden_pos}" if golden_pos else "—",
              s.loc[s["team"] == M.MY_TEAM, "projected_stage"].iloc[0] if golden_pos else None)
    leader = s.iloc[0]
    c3.metric("Leader", leader["team"], f"{leader[rank_metric]:.1f} {rank_metric}")

    show = s[["pos", "team", "captain"] + round_cols + ["average", "total", "momentum", "trend", "projected_stage"]].copy()
    show = show.rename(columns={"pos": "#", "momentum": "R1→latest Δ", "trend": "trend/round"})

    def hl(row):
        color = ""
        if row["team"] == M.MY_TEAM:
            color = "background-color:#fff3cd;color:#222"      # gold
        elif row["projected_stage"] == "🏅 Final":
            color = "background-color:#d4edda;color:#222"      # green
        elif row["projected_stage"] == "❌ Out":
            color = "background-color:#f8d7da;color:#222"      # red
        return [color] * len(row)
    st.dataframe(show.style.apply(hl, axis=1).format(
        {**{c: "{:.1f}" for c in round_cols},
         "average": "{:.1f}", "total": "{:.1f}", "R1→latest Δ": "{:+.1f}", "trend/round": "{:+.2f}"},
        na_rep="—"), use_container_width=True, height=540, hide_index=True)
    st.caption(f"Projected stages use the sidebar cut-offs (QF≤{qf}, SF≤{sf}, Final≤{fin}). "
               "Golden RRR highlighted gold. These are projections from current scores, not official results.")

    # per-round line chart
    long = teams.dropna(subset=["team_total"]).copy()
    fig = px.line(long, x="round", y="team_total", color="team", markers=True,
                  title="Team score by round")
    fig.update_traces(line=dict(width=1), opacity=0.45)
    for tr in fig.data:
        if tr.name == M.MY_TEAM:
            tr.line.width = 5; tr.opacity = 1.0
    fig.update_layout(height=460, xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================= TEAMS
with tabs[1]:
    team = st.selectbox("Select team", sorted(teams["team"].unique()),
                        index=sorted(teams["team"].unique()).index(M.MY_TEAM)
                        if M.MY_TEAM in teams["team"].values else 0)
    trow = standings[standings["team"] == team].iloc[0]
    c = st.columns(4)
    c[0].metric("Captain", trow["captain"])
    c[1].metric("Rank (avg)", f"#{int(trow['rank'])}")
    c[2].metric("Average / round", f"{trow['average']:.1f}")
    c[3].metric("Momentum (R1→latest)", f"{trow['momentum']:+.1f}")

    tm = members[members["team"] == team].copy()
    st.markdown("#### Member scores by round")
    pivot = tm.pivot_table(index="member", columns="round", values="grand_total", aggfunc="first")
    pivot.columns = [f"R{int(x)}" for x in pivot.columns]
    pivot["avg"] = pivot.mean(axis=1)
    pivot = pivot.sort_values("avg", ascending=False)
    st.dataframe(pivot.style.format("{:.1f}", na_rep="—")
                 .background_gradient(cmap="Greens", text_color_threshold=0.4,
                                      subset=[c for c in pivot.columns if c != "avg"]),
                 use_container_width=True)
    n_round_cols = len([c for c in pivot.columns if c != "avg"])
    subs = [m for m in pivot.index if pivot.loc[m, [c for c in pivot.columns if c != "avg"]].notna().sum() < n_round_cols]
    if subs:
        st.caption(f"🔄 **Substitutes / rotation:** {', '.join(subs)} did not perform every round "
                   f"(blank = '—'). A team may field a 6th singer as a sub, swapped across rounds — so "
                   f"partial round results for some singers are expected, not missing data. Averages use "
                   f"only the rounds each singer actually performed.")

    cc = st.columns(2)
    with cc[0]:
        st.markdown("#### Team strength profile")
        prof = M.criteria_profile(members[members["team"] == team])
        comp = M.criteria_profile(members)
        cats = [M.CRITERIA_LABELS[k] for k in prof]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=list(comp.values()), theta=cats, name="All teams avg",
                                      fill="toself", opacity=0.3))
        fig.add_trace(go.Scatterpolar(r=list(prof.values()), theta=cats, name=team, fill="toself"))
        fig.update_layout(polar=dict(radialaxis=dict(range=[7.5, 10])), height=380,
                          margin=dict(t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with cc[1]:
        st.markdown("#### Judge feedback (decoded ✅ / ⚠️)")
        rsel = st.selectbox("Round", sorted(tm["round"].dropna().unique()), key="fb_round")
        for _, r in tm[tm["round"] == rsel].iterrows():
            with st.expander(f"{r['member']} — {r['grand_total']:.1f}"):
                ins = INSIGHTS.get((team, int(rsel), r["member"]))
                if ins:
                    if ins.get("positives"):
                        st.markdown("**✅ Positives:** " + " · ".join(ins["positives"]))
                    if ins.get("negatives"):
                        st.markdown("**⚠️ To improve:** " + " · ".join(ins["negatives"]))
                    if ins.get("focus"):
                        st.caption("Focus criteria: " + ", ".join(ins["focus"]))
                    with st.popover("Raw Tanglish feedback"):
                        st.write(r["feedback"] or "_none_")
                else:
                    st.write(r["feedback"] or "_no feedback recorded_")

# ============================================================================= INDIVIDUALS
with tabs[2]:
    ms = M.member_standings(members)
    st.markdown("#### 🏆 Top performer of each team")
    top = M.top_per_team(members)[["team", "member", "avg_grand", "best_grand", "trend"]]
    st.dataframe(top.rename(columns={"avg_grand": "avg", "best_grand": "best", "trend": "trend/round"})
                 .style.format({"avg": "{:.1f}", "best": "{:.1f}", "trend/round": "{:+.2f}"})
                 .background_gradient(cmap="Blues", subset=["avg"])
                 .background_gradient(cmap="Greens", subset=["best"]),
                 use_container_width=True, height=420, hide_index=True)
    st.caption("avg (blue) = consistency · best (green) = ceiling / potential.")

    st.markdown("#### All performers ranked")
    q = st.text_input("Search performer / team")
    view = ms[["team", "member", "rounds", "avg_grand", "total_grand", "best_grand", "trend"]].copy()
    if q:
        m = view.apply(lambda r: q.lower() in str(r["member"]).lower()
                       or q.lower() in str(r["team"]).lower(), axis=1)
        view = view[m]
    view.insert(0, "rank", range(1, len(view) + 1))
    st.dataframe(view.rename(columns={"avg_grand": "avg", "total_grand": "total", "best_grand": "best",
                                      "trend": "trend/round"})
                 .style.format({"avg": "{:.1f}", "total": "{:.1f}", "best": "{:.1f}", "trend/round": "{:+.2f}"})
                 .background_gradient(cmap="Blues", subset=["avg"])
                 .background_gradient(cmap="Greens", subset=["best"]),
                 use_container_width=True, height=420, hide_index=True)

# ============================================================================= GOLDEN RRR WAR ROOM
with tabs[3]:
    if M.MY_TEAM not in teams["team"].values:
        st.warning("Golden RRR not found in data.")
    else:
        st.markdown(f"## 🎯 {M.MY_TEAM} — strategy war room")
        s = standings.sort_values(rank_metric, ascending=False).reset_index(drop=True)
        s["pos"] = range(1, len(s) + 1)
        my = s[s["team"] == M.MY_TEAM].iloc[0]
        pos = int(my["pos"])
        leader = s.iloc[0]
        ahead = s[s["pos"] < pos]
        target = s.iloc[max(0, fin - 1)]  # team on the final cut line

        c = st.columns(4)
        c[0].metric("Current rank", f"#{pos} / {len(s)}")
        c[1].metric("Gap to #1", f"{leader[rank_metric] - my[rank_metric]:+.1f}", leader["team"])
        c[2].metric(f"Gap to Final cut (#{fin})", f"{my[rank_metric] - target[rank_metric]:+.1f}",
                    "inside" if pos <= fin else "outside")
        c[3].metric("Momentum", f"{my['momentum']:+.1f}", "R1 → latest")

        # ---- per-criterion gap vs the teams ranked above Golden RRR
        st.markdown("### Where Golden RRR wins & loses (per criterion)")
        mine = M.criteria_profile(members[members["team"] == M.MY_TEAM])
        rivals_names = ahead["team"].tolist() or [leader["team"]]
        rivals = M.criteria_profile(members[members["team"].isin(rivals_names)])
        cats = [M.CRITERIA_LABELS[k] for k in mine]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=list(rivals.values()), theta=cats,
                                      name="Teams above you (avg)", fill="toself", opacity=0.4))
        fig.add_trace(go.Scatterpolar(r=list(mine.values()), theta=cats,
                                      name="Golden RRR", fill="toself"))
        fig.update_layout(polar=dict(radialaxis=dict(range=[7.5, 10])), height=400)
        colL, colR = st.columns([1, 1])
        colL.plotly_chart(fig, use_container_width=True)
        gaps = pd.DataFrame({"criterion": [M.CRITERIA_LABELS[k] for k in mine],
                             "golden": list(mine.values()),
                             "rivals_above": [rivals[k] for k in mine]})
        gaps["gap"] = gaps["golden"] - gaps["rivals_above"]
        gaps = gaps.sort_values("gap")
        with colR:
            st.markdown("**Your weakest criteria vs the teams above you** (most negative = biggest opportunity):")
            st.dataframe(gaps.style.format({"golden": "{:.2f}", "rivals_above": "{:.2f}", "gap": "{:+.2f}"})
                         .background_gradient(cmap="RdYlGn", subset=["gap"]),
                         use_container_width=True, hide_index=True)
            worst = gaps.iloc[0]
            st.error(f"Biggest gap: **{worst['criterion']}** ({worst['gap']:+.2f}). Focus rehearsal here.")

        # ---- rival threats and their advantage
        st.markdown("### Rival threats — what each team above you is best at")
        rows = []
        for rt in rivals_names:
            prof = M.criteria_profile(members[members["team"] == rt])
            best_k = max(prof, key=prof.get)
            tr = standings[standings["team"] == rt].iloc[0]
            rows.append({"team": rt, "captain": tr["captain"], "avg/round": tr["average"],
                         "trend": tr["trend"], "strongest": M.CRITERIA_LABELS[best_k],
                         "their_best_score": prof[best_k]})
        if rows:
            st.dataframe(pd.DataFrame(rows).style.format(
                {"avg/round": "{:.1f}", "trend": "{:+.2f}", "their_best_score": "{:.2f}"}),
                use_container_width=True, hide_index=True)
        else:
            st.success("Golden RRR is currently #1 — defend the lead; watch the highest-trend teams below.")

        # ---- which Golden RRR members to coach
        st.markdown("### Your roster — who to lift")
        gm = M.member_standings(members)
        gm = gm[gm["team"] == M.MY_TEAM][["member", "avg_grand", "best_grand", "trend"]]
        gm = gm.sort_values("avg_grand")
        st.dataframe(gm.rename(columns={"avg_grand": "avg", "best_grand": "best", "trend": "trend/round"})
                     .style.format({"avg": "{:.1f}", "best": "{:.1f}", "trend/round": "{:+.2f}"})
                     .background_gradient(cmap="RdYlGn", subset=["avg"])
                     .background_gradient(cmap="RdYlGn", subset=["best"]),
                     use_container_width=True, hide_index=True)

        # ---- per-singer: which criterion to improve + decoded judge suggestion
        st.markdown("### 🎯 Who improves what — per-singer focus")
        st.caption("Each singer's weakest criterion (their lowest average) and the judges' own suggestion, "
                   "decoded from the Tanglish feedback.")
        mc = M.member_criteria(members)
        mine_mc = mc[mc["team"] == M.MY_TEAM].sort_values("avg_grand")
        gmem = members[members["team"] == M.MY_TEAM]
        for _, row in mine_mc.iterrows():
            wk, wlabel, wscore = M.weakest_criterion(row)
            field_rank = None
            if wk:
                col = f"avg_{wk}"
                allm = mc.dropna(subset=[col])
                field_rank = int((allm[col] > row[col]).sum() + 1)
            ins = M.member_insight(INSIGHTS, M.MY_TEAM, row["member"])
            rank_txt = f", ranks #{field_rank}/{len(mc)} among all singers on it" if field_rank else ""
            head = f"**{row['member']}** (avg {row['avg_grand']:.1f}) → improve **{wlabel}** ({wscore:.2f}{rank_txt})"
            with st.expander(head, expanded=False):
                if ins["negatives"]:
                    st.markdown(f"**⚠️ Judges want fixed:** {' · '.join(ins['negatives'])}")
                if ins["focus"]:
                    st.markdown(f"**Criteria to drill:** {', '.join(ins['focus'])}")
                if ins["positives"]:
                    st.markdown(f"**✅ Keep doing:** {' · '.join(ins['positives'])}")
                if not ins["negatives"] and not ins["focus"]:
                    st.markdown("No explicit improvement noted — work the weakest criterion above.")

        st.caption("💬 For full per-round judge feedback on each Golden RRR singer, see the "
                   "**🎤 Teams** tab → select Golden RRR → Judge feedback.")

# ============================================================================= BEAT A TEAM
with tabs[4]:
    st.markdown("## 🥊 Beat a Team — head-to-head game plan")
    st.caption("Pick the team you have to beat. This shows what they're strongest at (their edge you must "
               "neutralise) and where Golden RRR already beats them (lean in). Built for knockout rounds.")

    others = [t for t in sorted(teams["team"].unique()) if t != M.MY_TEAM]
    # default to the nearest team above Golden RRR in the standings
    s = standings.sort_values(rank_metric, ascending=False).reset_index(drop=True)
    s["pos"] = range(1, len(s) + 1)
    my_pos = int(s.loc[s["team"] == M.MY_TEAM, "pos"].iloc[0]) if (s["team"] == M.MY_TEAM).any() else 1
    nearest = s.loc[s["pos"] == max(1, my_pos - 1), "team"].iloc[0]
    rival = st.selectbox("Team to beat", others,
                         index=others.index(nearest) if nearest in others else 0)

    df, their_edge, your_edge = M.matchup(members, M.MY_TEAM, rival)
    a_avg = standings.loc[standings["team"] == M.MY_TEAM, "average"].iloc[0]
    b_avg = standings.loc[standings["team"] == rival, "average"].iloc[0]
    b_cap = standings.loc[standings["team"] == rival, "captain"].iloc[0]

    c = st.columns(3)
    c[0].metric("Golden RRR avg/round", f"{a_avg:.1f}")
    c[1].metric(f"{rival} avg/round", f"{b_avg:.1f}", f"captain {b_cap}")
    c[2].metric("Overall margin", f"{a_avg - b_avg:+.1f}",
                "ahead" if a_avg >= b_avg else "behind")

    colL, colR = st.columns([1, 1])
    with colL:
        cats = [M.CRITERIA_LABELS[k] for k in M.CRITERIA if f"avg_{k}" in members.columns]
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=[df[df["criterion"] == cc][rival].iloc[0] for cc in cats],
                                      theta=cats, name=rival, fill="toself", opacity=0.45))
        fig.add_trace(go.Scatterpolar(r=[df[df["criterion"] == cc][M.MY_TEAM].iloc[0] for cc in cats],
                                      theta=cats, name="Golden RRR", fill="toself"))
        fig.update_layout(polar=dict(radialaxis=dict(range=[7.5, 10])), height=380,
                          margin=dict(t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with colR:
        st.dataframe(df[["criterion", M.MY_TEAM, rival, "diff", "verdict"]]
                     .style.format({M.MY_TEAM: "{:.2f}", rival: "{:.2f}", "diff": "{:+.2f}"})
                     .background_gradient(cmap="RdYlGn", subset=["diff"]),
                     use_container_width=True, hide_index=True)

    st.markdown("### 📋 Game plan")
    if not their_edge.empty:
        worst = their_edge.iloc[0]
        bullets = ", ".join(f"**{r['criterion']}** (them {r[rival]:.2f} vs you {r[M.MY_TEAM]:.2f})"
                            for _, r in their_edge.iterrows())
        st.error(f"🔴 **Their edge — close these to beat them:** {bullets}.\n\n"
                 f"Top priority: **enhance {worst['criterion']}** — it's where {rival} hurts you most "
                 f"({worst['diff']:+.2f}).")
    else:
        st.success(f"🔴 You match or beat {rival} on every criterion — press your advantage everywhere.")
    if not your_edge.empty:
        bullets = ", ".join(f"**{r['criterion']}** (you {r[M.MY_TEAM]:.2f} vs them {r[rival]:.2f})"
                            for _, r in your_edge.iterrows())
        st.success(f"🟢 **Your edge — lean in (pick songs that show these off):** {bullets}.")
    if a_avg >= b_avg:
        st.info(f"Overall you're **ahead by {a_avg - b_avg:.1f}**. Defend it: hold your edges and don't "
                f"concede their strong criteria.")
    else:
        st.warning(f"Overall you trail by **{b_avg - a_avg:.1f}**. Focus rehearsal on their edge above — "
                   f"that's the fastest way to flip this matchup.")

    # rival's threat singers + decoded judge feedback
    st.markdown(f"### ⚠️ {rival}'s threat singers (who scores well — watch these)")
    rm = M.member_standings(members)
    rstars = rm[rm["team"] == rival].sort_values("avg_grand", ascending=False).head(3)
    rmem = members[members["team"] == rival]
    # Golden RRR's ceiling — the best single score any of our singers has hit
    g_best = float(rm[rm["team"] == M.MY_TEAM]["best_grand"].max())
    g_best_who = rm[rm["team"] == M.MY_TEAM].sort_values("best_grand", ascending=False)["member"].iloc[0]
    st.caption(f"Your ceiling to beat: **{g_best_who} {g_best:.1f}** (Golden RRR's highest single score). "
               f"🔥 = their *best* score tops yours — high potential even if their average looks lower.")
    for _, r0 in rstars.iterrows():
        rounds_played = sorted(int(x) for x in rmem[rmem["member"] == r0["member"]]["round"].dropna().unique())
        sub_tag = "" if len(rounds_played) >= len(all_rounds) else f" · plays R{rounds_played} (sub/partial)"
        ceiling_flag = " 🔥 best beats your ceiling" if r0["best_grand"] > g_best else ""
        with st.expander(f"🎤 {r0['member']} — avg {r0['avg_grand']:.1f}, **best {r0['best_grand']:.1f}**, "
                         f"trend {r0['trend']:+.2f}{ceiling_flag}{sub_tag}", expanded=False):
            if r0["best_grand"] > g_best:
                st.markdown(f"🔥 **Top-potential threat:** their best ({r0['best_grand']:.1f}) is higher than "
                            f"Golden RRR's best ({g_best:.1f}). On their day they out-sing your strongest.")
            # decoded judge insights aggregated across their rounds
            ins = M.member_insight(INSIGHTS, rival, r0["member"])
            if ins["positives"]:
                st.markdown(f"**✅ Their strengths (what makes them a threat):** {' · '.join(ins['positives'])}")
            if ins["negatives"]:
                st.markdown(f"**⚠️ Their weaknesses (out-sing them here):** {' · '.join(ins['negatives'])}")
            if ins["focus"]:
                st.markdown(f"**Exploit criteria:** {', '.join(ins['focus'])}.")
            fbrows = rmem[rmem["member"] == r0["member"]].sort_values("round")
            with st.popover("Show raw judge feedback"):
                for _, fr in fbrows.iterrows():
                    st.markdown(f"**R{int(fr['round'])} ({fr['grand_total']:.1f}):** {fr['feedback'] or '—'}")
    st.caption("‘Threat singers’ = highest-scoring members of the rival. ✅/⚠️ are LLM-decoded from the "
               "Tanglish judge feedback across all their rounds — strengths to respect, weaknesses to attack.")

    # rival's weak links — singers Golden RRR can beat easily
    st.markdown(f"### 🟢 {rival} singers you can beat easily (weak links to target)")
    threat_names = set(rstars["member"])
    weak = rm[(rm["team"] == rival) & (~rm["member"].isin(threat_names))].sort_values("avg_grand").head(3)
    if weak.empty:
        st.caption(f"{rival}'s roster is balanced — no clear weak link. Win on the criteria gaps above instead.")
    else:
        st.caption("Their lowest-scoring members — target these head-to-heads. The judge flags show exactly "
                   "where they're vulnerable, so you know which of your singers to match against them.")
        for _, w0 in weak.iterrows():
            rp = sorted(int(x) for x in rmem[rmem["member"] == w0["member"]]["round"].dropna().unique())
            sub_tag = "" if len(rp) >= len(all_rounds) else f" · plays R{rp} (sub/partial)"
            with st.expander(f"🎤 {w0['member']} — avg {w0['avg_grand']:.1f}, best {w0['best_grand']:.1f}, "
                             f"trend {w0['trend']:+.2f}{sub_tag}", expanded=False):
                ins = M.member_insight(INSIGHTS, rival, w0["member"])
                if ins["negatives"]:
                    st.markdown(f"**⚠️ Where they're vulnerable (press here):** {' · '.join(ins['negatives'])}")
                if ins["focus"]:
                    st.markdown(f"**Exploit criteria:** {', '.join(ins['focus'])}.")
                if ins["positives"]:
                    st.caption(f"(They're still decent at: {' · '.join(ins['positives'])} — don't underestimate.)")
                if not ins["negatives"] and not ins["focus"]:
                    st.markdown("Lowest scorer on the team — your safest matchup to win.")
                fbrows = rmem[rmem["member"] == w0["member"]].sort_values("round")
                with st.popover("Show raw judge feedback"):
                    for _, fr in fbrows.iterrows():
                        st.markdown(f"**R{int(fr['round'])} ({fr['grand_total']:.1f}):** {fr['feedback'] or '—'}")

    st.divider()
    st.markdown(f"### 🗺️ Criterion ranks across all 21 teams — Golden RRR vs {rival}")
    st.caption("1 = best in the whole competition. Updates with the team you pick above — compare where each of "
               "you is strong (green) or weak (red) field-wide.")
    mat, ranks = M.team_criteria_matrix(members)
    field = pd.DataFrame({
        "criterion": list(mat.columns),
        "Golden avg": [mat.loc[M.MY_TEAM, c] for c in mat.columns],
        "Golden rank": [int(ranks.loc[M.MY_TEAM, f"{c} rank"]) for c in mat.columns],
        f"{rival} avg": [mat.loc[rival, c] for c in mat.columns],
        f"{rival} rank": [int(ranks.loc[rival, f"{c} rank"]) for c in mat.columns],
        "field best": [mat[c].max() for c in mat.columns],
        "best team": [mat[c].idxmax() for c in mat.columns],
    }).sort_values("Golden rank", ascending=False)
    st.dataframe(field.style.format({"Golden avg": "{:.2f}", f"{rival} avg": "{:.2f}", "field best": "{:.2f}"})
                 .background_gradient(cmap="RdYlGn_r", subset=["Golden rank", f"{rival} rank"], vmin=1, vmax=21),
                 use_container_width=True, hide_index=True)
    worstc = field.iloc[0]
    st.markdown(f"➡️ **Your biggest field-wide liability: {worstc['criterion']}** — you rank "
                f"**#{int(worstc['Golden rank'])}/21**, {rival} ranks **#{int(worstc[f'{rival} rank'])}/21** "
                f"(field best: {worstc['best team']} {worstc['field best']:.2f}).")

# ============================================================================= DATA NOTES
with tabs[5]:
    st.markdown("#### Data provenance & known issues")
    st.markdown("""
- Extracted from 64 scorecard images via vision OCR, then **arithmetic-audited**
  (every grand total reconciled against J1+J2 and team totals).
- **Captain** = the name on header line 2 of each card (not always the first-listed member).
- **Rounds** assigned by the official rule: *earliest year = Round 1, next year = Round 2…*
  (this corrected ISAI SARAL's IMG_3573, mislabelled "Round 1" on the sheet but year 1993 ⇒ Round 2).
- **Duplicates removed:** Golden RRR had two identical screenshots each for R1 and R3.
""")
    issues = []
    vt = standings[standings["team"] == "VOCAL TRADERS"]
    if not vt.empty and vt["rounds_played"].iloc[0] < len(all_rounds):
        issues.append("**VOCAL TRADERS** has no Round 3 card in the current image set.")
    issues.append("**SM RAAGA REBELS R1**: the sheet's printed Team Total (450.5) is 5 higher than the sum "
                  "of member grand totals — Nethaji's −5 (Year compliance NO) penalty wasn't reflected in the "
                  "team total on the card. Shown as printed.")
    issues.append("**Substitutes are expected, not errors:** a team may have up to 6 singers and rotate a "
                  "substitute across rounds, so some singers legitimately have results for only some rounds. "
                  "All averages use only the rounds a singer actually performed.")
    issues.append("A few per-judge sub-totals (J1/J2 Total columns) were OCR-ambiguous; these don't affect "
                  "grand totals or any ranking — only the radar per-criterion averages, marginally.")
    for i in issues:
        st.markdown(f"- {i}")
    st.markdown("#### Raw tables")
    st.download_button("Download members.csv", members.to_csv(index=False), "members.csv")
    st.download_button("Download teams.csv", teams.to_csv(index=False), "teams.csv")
