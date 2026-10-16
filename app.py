"""Elevate Scheduling Model - Capstone II v1 (Tier 4, Python / Streamlit).
BUAD 583 - Brandon Stanley - Elevate Oral Surgery.
No API keys, no external AI service: a rule-based plan reader plus a linear regression model."""
import math, datetime as dt
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm
import streamlit as st
from plan_reader import read_plan
from test_plans import TESTS, VARIANTS

st.set_page_config(page_title="Elevate Scheduling", page_icon="🦷", layout="centered")
HERE = Path(__file__).parent
FEATURES = ["teeth_removed", "full_bony", "graft_implant_alveo", "prf", "new_clock"]
OLD_BLOCK, WALK, COLS = 60, 2, 3
CRITERIA = {"mae": 10, "cover": 0.80, "reader_exact": 0.90}


# ---------------- data + model ----------------
@st.cache_data
def base_cases():
    df = pd.read_csv(HERE / "elevate_cases.csv")
    df["new_clock"] = (df["source"] != "starting log").astype(int)
    return df

if "recorded" not in st.session_state:
    st.session_state.recorded = []

def all_cases():
    df = base_cases()
    if st.session_state.recorded:
        df = pd.concat([df, pd.DataFrame(st.session_state.recorded)], ignore_index=True)
    return df

def fit_model(df):
    X = sm.add_constant(df[FEATURES].astype(float), has_constant="add")
    m = sm.OLS(df["surgeon_minutes"].astype(float), X).fit()
    res = m.resid[df["new_clock"] == 1]
    use = res if len(res) >= 5 else m.resid
    timed = df[df["new_clock"] == 1].dropna(subset=["seated_to_surgeon_in", "surgeon_out_to_discharged"])
    ok = len(timed) >= 5
    return {"params": m.params.to_dict(), "ols": m, "cushion": max(0.0, float(np.quantile(use, 0.8))),
            "pre": float(timed["seated_to_surgeon_in"].mean()) if ok else 8.0,
            "post": float(timed["surgeon_out_to_discharged"].mean()) if ok else 10.0}

def estimate(teeth, full_bony=0, graft=0, prf=0, sedation=True, model=None):
    m = model or MODEL
    b = m["params"]; fb = min(full_bony, teeth)
    surgeon = max(1.0, b["const"] + b["teeth_removed"]*teeth + b["full_bony"]*fb
                  + b["graft_implant_alveo"]*graft + b["prf"]*prf + b["new_clock"])
    pre, post = (m["pre"], m["post"]) if sedation else (0.0, 0.0)
    block = int(math.ceil((pre + surgeon + m["cushion"] + post) / 5) * 5)
    flags = []
    if graft: flags.append("Graft, implant or alveoloplasty: only 13 of 111 training cases had one.")
    if not sedation: flags.append("Local case: the model was trained on sedation cases only.")
    if teeth > 24: flags.append("More teeth than any training case.")
    return {"surgeon": surgeon, "pre": pre, "post": post, "cushion": m["cushion"], "block": block, "flags": flags}

MODEL = fit_model(all_cases())
clk = lambda m: f"{int(m//60) % 12 or 12}:{int(m % 60):02d}"


# ---------------- page ----------------
st.title("Elevate Scheduling")
st.caption("Elevate Oral Surgery · BUAD 583 Capstone II v1 (Tier 4: Python). "
           "Reads a treatment plan and recommends how long to book from patient seated to discharged. "
           "A person always makes the booking decision.")
tab_desk, tab_day, tab_rec, tab_eval, tab_about = st.tabs(["Desk", "Day plan", "Record", "Evaluation", "About"])

# ---- DESK ----
with tab_desk:
    st.markdown("**1.** Paste the procedure lines only, with no name, birth date or chart number. "
                "**2.** Click *Read plan* and check the counts. **3.** Use the recommendation.")
    plan = st.text_area("Treatment plan", "IV sedation. D7240 x4, teeth #1, 16, 17, 32. PRF.", height=90)
    if st.button("Read plan", type="primary"):
        r = read_plan(plan)
        st.session_state.read = r
        if not r["refused"]:
            st.session_state.update(d_teeth=max(1, r["teeth_removed"]), d_fb=r["full_bony"],
                                    d_graft=bool(r["graft"]), d_prf=bool(r["prf"]),
                                    d_sed="IV sedation" if r["sedation"] else "Local only")
    r = st.session_state.get("read")
    if r and r["refused"]:
        st.error("Refused: " + r["notes"][0])
    elif r and r["notes"]:
        for n in r["notes"]:
            st.warning("Check: " + n)

    st.subheader("Case details (confirm before booking)")
    c1, c2 = st.columns(2)
    for k, v in dict(d_teeth=4, d_fb=4, d_graft=False, d_prf=True, d_sed="IV sedation").items():
        st.session_state.setdefault(k, v)
    teeth = c1.number_input("Teeth removed", 1, 32, key="d_teeth")
    fb = c2.number_input("Full-bony (D7240)", 0, 32, key="d_fb")
    graft = c1.checkbox("Graft / implant / alveoloplasty", key="d_graft")
    prf = c2.checkbox("PRF", key="d_prf")
    sed = st.radio("Anesthesia", ["IV sedation", "Local only"], horizontal=True, key="d_sed")

    e = estimate(int(teeth), int(fb), int(graft), int(prf), sed == "IV sedation")
    st.metric("Minutes to book (seated → discharged)", e["block"], delta=f"{e['block'] - OLD_BLOCK:+d} vs flat {OLD_BLOCK}",
              delta_color="off")
    st.write(f"Seated → surgeon in **{e['pre']:.0f}** · surgeon in room **{e['surgeon']:.0f}** · "
             f"cushion **{e['cushion']:.0f}** (covers 8 in 10 cases) · surgeon out → discharged **{e['post']:.0f}**")
    if e["flags"]:
        for f in e["flags"]:
            st.warning("Surgeon double-check: " + f)
    else:
        st.success("Routine: the scheduler can book this.")
    if st.button("Add to day plan"):
        st.session_state.setdefault("day", []).append(dict(teeth=int(teeth), full_bony=int(fb), graft=int(graft),
                                                           prf=int(prf), sedation=sed == "IV sedation"))
        st.toast("Added to the day plan")
    st.caption(f"Model: {len(all_cases())} cases. Typical miss on surgeon time is about ±10 min. Recommendation only.")

# ---- DAY PLAN ----
def layout(day, start):
    free, dr_free, rows = [start]*COLS, start, []
    for i, c in enumerate(day):
        e = estimate(**c)
        want = start + e["pre"] if i == 0 else dr_free + WALK
        seat = max(start, math.floor((want - e["pre"]) / 5) * 5)
        col = next((k for k, f in enumerate(free) if f <= seat), None)
        if col is None:
            col = int(np.argmin(free)); seat = math.ceil(free[col] / 5) * 5
        dr_in = max(want, seat + e["pre"]); dr_out = dr_in + e["surgeon"]
        end = max(seat + e["block"], math.ceil((dr_out + e["post"] + e["cushion"]) / 5) * 5)
        free[col], dr_free = end, dr_out
        rows.append(dict(case=i+1, col=col+1, seat=seat, dr_in=dr_in, dr_out=dr_out, end=end, nflags=len(e["flags"]), **c))
    return pd.DataFrame(rows)

EXAMPLE_DAY = [dict(teeth=4, full_bony=4, prf=1), dict(teeth=1), dict(teeth=3, full_bony=1, prf=1),
               dict(teeth=2, graft=1, prf=1), dict(teeth=1, sedation=False), dict(teeth=4, full_bony=2, prf=1),
               dict(teeth=6), dict(teeth=1, graft=1), dict(teeth=4, prf=1)]

with tab_day:
    st.markdown(f"Three assistant columns. The surgeon goes room to room with {WALK} minutes between cases, "
                "so the dark bands (surgeon in room) never overlap.")
    b1, b2, b3 = st.columns(3)
    if b1.button("Load example day"): st.session_state.day = list(EXAMPLE_DAY)
    if b2.button("Clear day"): st.session_state.day = []
    start_t = b3.time_input("First seat", dt.time(8, 0), step=300)
    day = st.session_state.get("day", [])
    if not day:
        st.info("No cases yet. Add cases from the Desk tab, or load the example day (made-up cases).")
    else:
        start = start_t.hour * 60 + start_t.minute
        p = layout(day, start)
        k1, k2 = st.columns(2)
        k1.metric("Last block ends", clk(p.end.max()))
        k2.metric(f"Same cases, one room at {OLD_BLOCK} min", clk(start + OLD_BLOCK * len(day)))
        fig, ax = plt.subplots(figsize=(6, 6))
        for _, r in p.iterrows():
            ax.bar(r.col, r.end - r.seat, bottom=r.seat, width=0.8, color="#D5E3EC", edgecolor="#5A6D80")
            ax.bar(r.col, r.dr_out - r.dr_in, bottom=r.dr_in, width=0.8, color="#17799A")
            ax.text(r.col, r.seat + 3, f"#{r.case} {clk(r.seat)}", ha="center", va="top", fontsize=8)
        ax.invert_yaxis(); ax.set_xticks([1, 2, 3], ["Col 1", "Col 2", "Col 3"])
        ticks = list(range(int(p.seat.min()) // 60 * 60, int(p.end.max()) + 60, 60))
        ax.set_yticks(ticks, [clk(t) for t in ticks]); ax.set_title("Light: seated→discharged · Dark: surgeon in room", fontsize=10)
        st.pyplot(fig)
        st.dataframe(pd.DataFrame({"Seat": p.seat.map(clk), "Col": p.col, "Book (min)": (p.end - p.seat).astype(int),
                                   "Dr in": p.dr_in.map(clk), "Dr out": p.dr_out.map(clk), "Teeth": p.teeth,
                                   "Flag": np.where(p["nflags"] > 0, "Surgeon double-check", "")}), hide_index=True)
        st.caption("Recommended times. The scheduler books them in Sensei by hand.")

# ---- RECORD ----
STAGES = ["Patient seated", "Surgeon in", "Surgeon out", "Discharged"]
with tab_rec:
    st.markdown("Set the case, then tap once at each stage. When the case is saved, the model refits.")
    c1, c2 = st.columns(2)
    r_teeth = c1.number_input("Teeth", 1, 32, 1, key="r_teeth")
    r_fb = c2.number_input("Full-bony", 0, 32, 0, key="r_fb")
    r_graft = c1.checkbox("Graft / implant", key="r_graft")
    r_prf = c2.checkbox("PRF", key="r_prf")
    times = st.session_state.setdefault("times", {})
    nxt = STAGES[len(times)]
    if st.button(f"Tap: {nxt}", type="primary", use_container_width=True):
        times[nxt] = dt.datetime.now()
        if len(times) == len(STAGES):
            mins = lambda a, b: round((times[b] - times[a]).total_seconds() / 60, 1)
            st.session_state.recorded.append({
                "case_id": f"R{len(st.session_state.recorded)+1:02d}", "source": "recorded in app",
                "teeth_removed": int(r_teeth), "full_bony": int(min(r_fb, r_teeth)), "graft_implant_alveo": int(r_graft),
                "prf": int(r_prf), "surgeon_minutes": mins("Surgeon in", "Surgeon out"), "clock": "surgeon in to out",
                "seated_to_surgeon_in": mins("Patient seated", "Surgeon in"),
                "surgeon_out_to_discharged": mins("Surgeon out", "Discharged"), "new_clock": 1})
            st.session_state.times = {}
            st.success("Case saved. The model now includes it.")
        st.rerun()
    for s in STAGES:
        if s in times: st.write(f"✓ {s}: {times[s]:%I:%M:%S %p}")
    if times and st.button("Cancel this case"):
        st.session_state.times = {}; st.rerun()
    if st.session_state.recorded:
        rec = pd.DataFrame(st.session_state.recorded)
        st.dataframe(rec[["case_id", "teeth_removed", "surgeon_minutes", "seated_to_surgeon_in", "surgeon_out_to_discharged"]], hide_index=True)
        st.download_button("Download recorded cases (CSV)", rec.to_csv(index=False), "elevate_recorded_cases.csv", "text/csv")
    st.caption("Cases recorded here last only for this browser session. Download them before closing the page.")

# ---- EVALUATION ----
@st.cache_data
def model_eval():
    cases = base_cases(); rows = []
    for idx, r in cases[cases.new_clock == 1].iterrows():
        m = fit_model(cases.drop(index=idx))
        e = estimate(int(r.teeth_removed), int(r.full_bony), int(r.graft_implant_alveo), int(r.prf), model=m)
        flat = cases.drop(index=idx).query("new_clock == 1")["surgeon_minutes"].mean()
        total = r.seated_to_surgeon_in + r.surgeon_minutes + r.surgeon_out_to_discharged
        err = e["surgeon"] - r.surgeon_minutes
        rows.append({"ID": r.case_id, "Input": f"{int(r.teeth_removed)}T {int(r.full_bony)}FB graft={int(r.graft_implant_alveo)} PRF={int(r.prf)}",
                     "Actual surgeon min": r.surgeon_minutes, "Predicted": round(e["surgeon"], 1), "Error": round(err, 1),
                     "Result": "Pass" if abs(err) <= 10 else "Partial" if abs(err) <= 20 else "Fail",
                     "Block": e["block"], "Actual total": total, "Fit block": "Pass" if total <= e["block"] else "Fail",
                     "Fit old 60": "Pass" if total <= OLD_BLOCK else "Fail", "_flat": abs(flat - r.surgeon_minutes)})
    return pd.DataFrame(rows)

def reader_eval(tests):
    out = []
    for tid, cat, text, exp in tests:
        r = read_plan(text)
        got = (r["teeth_removed"], r["full_bony"], r["graft"], r["prf"], None if r["refused"] else r["sedation"], r["refused"])
        flagged = bool(r["notes"]) or r["graft"] == 1 or r["sedation"] is False or r["teeth_removed"] > 24
        out.append({"ID": tid, "Type": cat, "Input": text, "Expected": str(exp[:6]), "Actual": str(got),
                     "Result": "Pass" if got == exp[:6] else ("Partial" if flagged else "Fail")})
    return pd.DataFrame(out)

with tab_eval:
    st.subheader("Duration model: leave-one-out on the 10 timed Elevate cases")
    ev = model_eval()
    k1, k2, k3 = st.columns(3)
    k1.metric("Surgeon-time MAE", f"{ev.Error.abs().mean():.1f} min", f"target ≤ {CRITERIA['mae']}", delta_color="off")
    k2.metric("Fit recommended block", f"{(ev['Fit block'] == 'Pass').mean():.0%}", f"target ≥ {CRITERIA['cover']:.0%}", delta_color="off")
    k3.metric("Fit old 60-min block", f"{(ev['Fit old 60'] == 'Pass').mean():.0%}", "baseline", delta_color="off")
    st.write(f"Plain-average baseline MAE: **{ev._flat.mean():.1f} min** · average recommended block **{ev.Block.mean():.0f} min**")
    st.dataframe(ev.drop(columns="_flat"), hide_index=True)
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(ev["Actual surgeon min"], ev.Predicted)
    lim = [0, max(ev["Actual surgeon min"].max(), ev.Predicted.max()) + 10]
    ax.plot(lim, lim, "--", color="gray", lw=1); ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Actual"); ax.set_ylabel("Predicted (held out)"); st.pyplot(fig)
    st.info("Ten cases from one short clinic week is a small sample. The model does not yet beat the plain average "
            "on surgeon time, and longer blocks buy most of the improvement in block fit. More timed cases are the next step.")

    st.subheader("Plan reader")
    for name, t, note in [("Development set", TESTS, "written alongside the rules, so this is optimistic"),
                          ("Phrasing variants (blind)", VARIANTS, "office shorthand, run once, not tuned")]:
        d = reader_eval(t)
        st.markdown(f"**{name}** ({note}): {(d.Result == 'Pass').mean():.0%} exact · "
                    f"{(d.Result == 'Partial').sum()} wrong but flagged · **{(d.Result == 'Fail').sum()} silent errors**")
        st.dataframe(d, hide_index=True)

    st.subheader("Model coefficients")
    st.dataframe(MODEL["ols"].summary2().tables[1].round(2))

# ---- ABOUT ----
with tab_about:
    st.markdown(f"""
**Workflow:** plan text → identifier screen (refuses names, birth dates and chart numbers) → rule-based reader →
**scheduler confirms the counts** (this check can't be skipped) → regression estimate → routing (routine: scheduler books /
flagged: surgeon double-check) → booked by hand in Sensei → assistant times the case → model refits.

**Model:** linear regression, `surgeon minutes ~ teeth + full-bony + graft + PRF + clock`, fit on 101 anesthesia-log cases
plus 10 timed Elevate cases (all de-identified). The block adds the average seated→surgeon-in and surgeon-out→discharged
times and a cushion equal to the 80th percentile of errors.

**Does not do yet:** read photos; handle free-text shorthand reliably; account for age, medical history or extraction
difficulty; connect to Sensei; keep recorded cases after the page is closed.

**Dependencies:** Python and Streamlit only. There is no external AI service or API key, so no AI vendor can change the price or turn it off.
""")
