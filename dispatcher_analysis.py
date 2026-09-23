"""Dispatcher / queue analyses for the OPD 911 project.

Builds three charts (written to the OPD Outputs folder in Box, prefixed `dispatch_`):

  1. dispatch_staffing_vs_answer_speed.png
     Dispatcher staffing (authorized, filled, recommended) from OPD staffing reports,
     alongside monthly 911 volume and % answered within 15s (answer-speed PDFs).
     -> Queue 1: waiting for a call taker.

  2. dispatch_p1_queue_vs_travel_by_hour.png
     Citywide Priority 1: median minutes waiting for dispatch vs. driving, by hour.
     -> Shows whether P1 delay spikes come from the dispatch queue or from travel.

  3. dispatch_queue_by_hour_by_area.png
     Median wait from incident created -> first unit dispatched, by hour, per Patrol
     Area, for P1 / P2 / P3, with patrol shift-start hours marked.
     -> Queue 2: waiting for an available officer.

Sources (all in Box, "02 Oakland Police Dept (OPD)"):
  - Data/Our Data/harmonized_calls_2021_2026.parquet
  - Data/Our Data/911-answering-speed-2025-q4.pdf, 911-answering-speed-2026-jan-july.pdf
    (values transcribed below)
  - Data/Our Data/OPD Reports/* staffing reports (dispatcher vacancy table, transcribed below)
  - Outputs/opd_patrol_shift_structure.csv
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box_utils import BOX_ROOT

OPD = BOX_ROOT / "OPD & TAN - Core Workspace" / "02 Oakland Police Dept (OPD)"
DATA = OPD / "Data/Our Data"
OUT = OPD / "Outputs"
YEAR = 2025  # last full calendar year in the CAD extract

AREA_BEATS = {1: (1, 7), 2: (8, 13), 3: (14, 19), 4: (20, 25), 5: (26, 30), 6: (31, 35)}
PRI_COLORS = {1: "#d62728", 2: "#1f77b4", 3: "#7f7f7f"}

plt.rcParams.update({
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e6e6e6",
    "axes.titlelocation": "left", "axes.titlesize": 12,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
})

# --- Transcribed source tables ---------------------------------------------------------

# "Professional Staff Vacancies" table, Police Communications Dispatcher row.
DISPATCHER_STAFFING = pd.DataFrame([
    ("2022-03-31", 86, 17), ("2022-09-30", 86, 12), ("2022-12-31", 86, 12),
    ("2023-03-31", 86, 13), ("2023-09-30", 86, 16), ("2023-12-31", 86, 8),
    ("2024-06-30", 78, 10), ("2025-06-17", 78, 11), ("2026-02-28", 78, 12),
], columns=["as_of", "authorized", "vacancies"])
RECOMMENDED_FRONTLINE = 90  # 2018/2019 OPD staffing study (cited by PFM + City Auditor)

# "911 Answering Speed — Vesta Call Count by Wait Time Range" (monthly).
# (month, total 911 calls, % answered within 15 s)
ANSWER_SPEED = pd.DataFrame([
    ("2025-01", 25161, 75), ("2025-02", 22809, 75), ("2025-03", 27877, 76),
    ("2025-04", 24610, 72), ("2025-05", 26250, 69), ("2025-06", 24901, 72),
    ("2025-07", 26375, 75), ("2025-08", 26733, 71), ("2025-09", 26636, 67),
    ("2025-10", 25469, 67), ("2025-11", 23937, 75), ("2025-12", 25638, 69),
    ("2026-01", 26260, 73), ("2026-02", 23334, 74), ("2026-03", 26088, 74),
    ("2026-04", 24802, 77), ("2026-05", 29860, 73), ("2026-06", 30814, 74),
    ("2026-07", 27535, 79),
], columns=["month", "calls_911", "pct_15s"])
STATE_STANDARD_PCT = 90


def beat_to_area(beat):
    digits = "".join(ch for ch in str(beat) if ch.isdigit())
    if not digits:
        return np.nan
    n = int(digits)
    for area, (lo, hi) in AREA_BEATS.items():
        if lo <= n <= hi:
            return area
    return np.nan


def load_calls():
    d = pd.read_parquet(DATA / "harmonized_calls_2021_2026.parquet")
    # Public-initiated calls only (2024+ labels); officer/MDT-initiated activity excluded.
    d = d[(d.event_time.dt.year == YEAR) & d.call_source.isin(["911", "Phone"])]
    d = d.drop_duplicates("event_number")
    d["pri"] = pd.to_numeric(d.priority, errors="coerce")
    d["queue_min"] = (d.dispatch_time - d.event_time).dt.total_seconds() / 60
    d["travel_min"] = (d.arrival_time - d.dispatch_time).dt.total_seconds() / 60
    d.loc[d.queue_min < 0, "queue_min"] = np.nan
    d.loc[d.travel_min < 0, "travel_min"] = np.nan
    d["hour"] = d.event_time.dt.hour
    d["area"] = d.beat.map(beat_to_area)
    return d


def shift_starts():
    s = pd.read_csv(OUT / "opd_patrol_shift_structure.csv")
    s = s[s.as_of == s.as_of.max()]
    s["start"] = s.shift_hours.str[:2].astype(int)
    return s.groupby("area").start.apply(lambda x: sorted(set(x))).to_dict(), s.as_of.iloc[0]


# --- Chart 1: staffing vs answer speed ----------------------------------------------------

def chart_staffing_vs_answer_speed():
    st = DISPATCHER_STAFFING.assign(as_of=lambda x: pd.to_datetime(x.as_of),
                                    filled=lambda x: x.authorized - x.vacancies)
    an = ANSWER_SPEED.assign(month=lambda x: pd.to_datetime(x.month) + pd.offsets.MonthEnd(0) - pd.Timedelta(days=14))

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(14, 8.5), sharex=True, gridspec_kw={"hspace": 0.35})
    fig.suptitle("Queue 1 — 911 call takers: dispatcher staffing and answer speed", x=0.01, ha="left", fontsize=15)

    a1.step(st.as_of, st.authorized, where="post", color="#555", lw=1.5, label="authorized")
    a1.plot(st.as_of, st.filled, "o-", color="#1f77b4", lw=2, label="filled (authorized − vacancies)")
    for x, y, v in zip(st.as_of, st.filled, st.vacancies):
        a1.annotate(f"{v} vacant", (x, y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=7, color="#1f77b4")
    a1.axhline(RECOMMENDED_FRONTLINE, ls="--", color="k", lw=1)
    a1.text(st.as_of.min(), RECOMMENDED_FRONTLINE + 1, "90 recommended by 2018/19 staffing study", fontsize=8)
    a1.set_ylim(50, 100)
    a1.set_ylabel("Police Communications Dispatchers")
    a1.set_title(f"Dispatcher positions, OPD staffing reports (n = {len(st)} reports)")
    a1.legend(loc="lower left", fontsize=8, frameon=False)

    a2b = a2.twinx()
    a2b.bar(an.month, an.calls_911, width=20, color="#d9d9d9", zorder=0)
    a2b.set_ylabel("911 calls per month (bars)", color="#888")
    a2b.set_ylim(0, 60000)
    a2b.spines["right"].set_visible(True)
    a2b.grid(False)
    a2.set_zorder(a2b.get_zorder() + 1)
    a2.patch.set_visible(False)
    a2.plot(an.month, an.pct_15s, "o-", color="#d62728", lw=2)
    a2.axhline(STATE_STANDARD_PCT, ls="--", color="k", lw=1)
    a2.text(an.month.min(), STATE_STANDARD_PCT + 1, "state standard: 90% within 15 s", fontsize=8)
    a2.set_ylim(50, 100)
    a2.set_ylabel("% of 911 calls answered ≤ 15 s")
    a2.set_title(f"911 answer speed, monthly (n = {an.calls_911.sum():,} calls; Jan 2025 – Jul 2026)")
    a2.set_xlim(pd.Timestamp("2022-01-01"), pd.Timestamp("2026-09-30"))

    fig.text(0.01, 0.01, "Answer-speed data only exists in Box from Jan 2025, so the two series overlap for ~18 months. "
             "Hourly ECaTS data + shift sheets from OPD would allow a direct staffing-vs-performance test.",
             fontsize=8, color="#555")
    path = OUT / "dispatch_staffing_vs_answer_speed.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# --- Chart 2: P1 queue vs travel by hour ----------------------------------------------------

def chart_p1_queue_vs_travel(d):
    p1 = d[d.pri == 1]
    g = p1.groupby("hour").agg(queue=("queue_min", "median"), travel=("travel_min", "median"),
                               q90=("queue_min", lambda s: s.quantile(0.9)))
    fig, ax = plt.subplots(figsize=(13, 5.5))
    ax.plot(g.index, g.queue, "o-", color="#d62728", lw=2, label="waiting for dispatch (created → dispatched)")
    ax.plot(g.index, g.travel, "o-", color="#2ca02c", lw=2, label="travel (dispatched → arrived)")
    for h in (6, 7, 14, 21, 22):
        ax.axvline(h, color="#bbb", ls=":", lw=1)
    ax.text(14.1, ax.get_ylim()[1] * 0.95, "dotted = patrol shift starts", fontsize=8, color="#777", va="top")
    ax.set_xticks(range(24))
    ax.set_xlabel("hour of day (call received)")
    ax.set_ylabel("median minutes")
    ax.set_title(f"Priority 1, {YEAR}: where does the time go?  n = {len(p1):,} public calls", fontsize=14)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    path = OUT / "dispatch_p1_queue_vs_travel_by_hour.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path, g


# --- Chart 3: dispatch queue by hour, by Area, by priority -----------------------------------

def chart_queue_by_area(d):
    starts, as_of = shift_starts()
    fig, axes = plt.subplots(2, 3, figsize=(20, 10), sharey=True)
    fig.suptitle(f"Queue 2 — waiting for an officer: median minutes from incident created to first unit dispatched, "
                 f"by hour, {YEAR}, by Patrol Area", x=0.01, ha="left", fontsize=15)
    ticks = [1, 2, 5, 15, 30, 60, 120, 240, 480]
    for ax, (area, (lo, hi)) in zip(axes.flat, AREA_BEATS.items()):
        a = d[d.area == area]
        for pri, color in PRI_COLORS.items():
            s = a[a.pri == pri].groupby("hour").queue_min.median()
            ax.plot(s.index, s.values, "o-", ms=3, lw=1.8, color=color, label=f"P{pri}")
        for h in starts.get(area, []):
            ax.axvline(h, color="#bbb", ls=":", lw=1)
        ax.set_yscale("log")
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"{t}" if t < 60 else f"{t // 60}h" for t in ticks])
        ax.set_ylim(0.7, 700)
        ax.set_xticks(range(24))
        ax.set_xlabel("hour of day (call received)")
        n = a.pri.isin(PRI_COLORS).sum()
        ax.set_title(f"Area {area}  ·  beats {lo}–{hi}\nn = {n:,} P1–P3 calls")
    for ax in axes[:, 0]:
        ax.set_ylabel("median wait for dispatch (log scale; min / h)")
    axes[0, 0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.text(0.01, 0.005, f"Public calls (911 + phone) only; officer-initiated excluded; deduplicated by incident number. "
             f"Dotted lines = patrol watch start hours (opd_patrol_shift_structure.csv, as of {as_of}).",
             fontsize=8, color="#555")
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    path = OUT / "dispatch_queue_by_hour_by_area.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


if __name__ == "__main__":
    print(chart_staffing_vs_answer_speed())
    calls = load_calls()
    p, g = chart_p1_queue_vs_travel(calls)
    print(p)
    print(g.round(1).to_string())
    print(chart_queue_by_area(calls))
