"""
Decode Tanglish judge feedback into structured positives / negatives / focus-criteria
per singer-round, and store in data/insights.json (read by the dashboard).

This is an OFFLINE build step (the deployed app never calls an LLM — it just reads the
baked insights.json, so hosting stays free with no API key).

Usage:
  python analyze_feedback.py            # finds feedback NOT yet in insights.json (new rounds)
                                        # and either calls a free LLM (if a key is set) or
                                        # writes them to /tmp/fb_chunks/ for manual decoding.

Free-LLM option (for automation): set GEMINI_API_KEY (Google AI Studio free tier) and
  pip install google-generativeai
Then this script decodes the missing feedback automatically and appends to insights.json.
Without a key, it prepares the chunks and you can have Claude decode them (as done initially).
"""
import json, os, math, glob

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INSIGHTS = os.path.join(DATA, "insights.json")
CRITERIA = ["Pitch", "Rhythm", "Diction", "Feel/Attitude", "Overall Perf."]

PROMPT = """You analyze Tanglish (Tamil-in-English) singing-competition judge feedback (two judges' comments combined per singer). For each item return JSON with:
- positives: short English phrases the judges praised
- negatives: short English phrases needing improvement
- focus: which of these criteria the negatives map to: Pitch, Rhythm, Diction, Feel/Attitude, Overall Perf.
Glossary: sruthi/apaswaram=pitch; landing=ending notes; sangathi/fillers=ornaments; ucharippu/pronunciation/words=diction; dynamics/feel/attitude/energy=feel; thaalam/timing/beat=rhythm; humming/breath/stage=overall.
Items:
"""


def existing_keys():
    if not os.path.exists(INSIGHTS):
        return set(), []
    data = json.load(open(INSIGHTS))
    return {(d["team"], int(d["round"]), d["member"]) for d in data}, data


def missing_items():
    recs = json.load(open(os.path.join(DATA, "clean.json")))
    keys, _ = existing_keys()
    out = []
    for r in recs:
        for m in r["members"]:
            fb = (m.get("feedback") or "").strip()
            k = (r["team"], int(r["round"]), m["name"])
            if fb and k not in keys:
                out.append({"team": r["team"], "round": int(r["round"]),
                            "member": m["name"], "feedback": fb})
    return out


def decode_with_gemini(items):
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
    results = []
    for i in range(0, len(items), 20):
        batch = items[i:i + 20]
        payload = PROMPT + json.dumps([{"team": b["team"], "round": b["round"],
                                        "member": b["member"], "feedback": b["feedback"]} for b in batch])
        payload += '\nReturn ONLY a JSON array, one object per item with keys team, round, member, positives, negatives, focus.'
        resp = model.generate_content(payload)
        txt = resp.text.strip().lstrip("```json").rstrip("```").strip()
        results.extend(json.loads(txt))
    return results


def main():
    items = missing_items()
    if not items:
        print("insights.json is up to date — no new feedback to decode.")
        return
    print(f"{len(items)} feedback items not yet decoded.")
    _, existing = existing_keys()
    if os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY found — decoding with Gemini (free tier)...")
        new = decode_with_gemini(items)
        json.dump(existing + new, open(INSIGHTS, "w"), ensure_ascii=False, indent=1)
        print(f"Appended {len(new)} -> insights.json ({len(existing)+len(new)} total).")
    else:
        os.makedirs("/tmp/fb_chunks", exist_ok=True)
        N = max(1, math.ceil(len(items) / 50))
        size = math.ceil(len(items) / N)
        for k in range(N):
            json.dump(items[k*size:(k+1)*size],
                      open(f"/tmp/fb_chunks/new_chunk_{k}.json", "w"), ensure_ascii=False, indent=1)
        print(f"No LLM key set. Wrote {N} chunk(s) to /tmp/fb_chunks/new_chunk_*.json.")
        print("Decode them (Claude or any LLM) into data/raw_insights/, then re-run merge, "
              "OR set GEMINI_API_KEY and re-run this script.")


if __name__ == "__main__":
    main()
