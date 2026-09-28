"""Dispatcher story charts for the OPD 911 project — observed data only, no models.

Charts (written to OUT, default ./outputs_preview; pass --box to write to Box Outputs):
  story_1_phone_demand_vs_staffing_2024.png  911 calls, scheduled call takers and answer time, by hour
  story_2_answer_time_by_month_hour_2024.png the midday slowdown repeats every month
  story_5_calls_per_officer_by_area_2025.png call demand by Patrol Area vs patrol officers assigned

(story_3 and story_4 are dispatch_staffing_vs_answer_speed.png and dispatch_p1_queue_vs_travel_by_hour.png
from dispatcher_analysis.py.)

Sources (Box, "02 Oakland Police Dept (OPD)")
  Data/Our Data/2024_answer_time.csv                               911 calls + answer time by hour, Jan 1 - Jun 21 2024
  Data/Our Data/911_01Jan-21Jun2024_OPD_Average Call Duration.xls  same, by month (answer time = queue + ring)
  City Auditor 911 audit (Oct 2025), Exhibit 19                    scheduled minimum 911 call takers by hour (read off chart)
  Data/Our Data/harmonized_calls_2021_2026.parquet                 CAD calls, 2025
  Outputs/opd_patrol_officers_by_shift_day.csv                     patrol officers assigned per shift, by Area
The hourly phone data only exists for Jan 1 - Jun 21, 2024 (public records request 24-6237).
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box_utils import BOX_ROOT

OPD = BOX_ROOT / "OPD & TAN - Core Workspace" / "02 Oakland Police Dept (OPD)"
DATA = OPD / "Data/Our Data"
OUT = OPD / "Outputs" if "--box" in sys.argv else Path("outputs_preview")
OUT.mkdir(exist_ok=True)

DAYS_2024 = 173  # Jan 1 - Jun 21, 2024
MONTH_DAYS = {"January2024": 31, "February2024": 29, "March2024": 31,
              "April2024": 30, "May2024": 31, "01-21Jun2024": 21}
# City Auditor Exhibit 19: estimated minimum staffing for 911 call takers (FTE) by hour, 2023 schedule.
AUDIT_MIN_STAFF = [5, 5, 5, 3.1, 3.1, 2.5, 2.5, 2.6, 2.6, 4, 4, 5,
                   5, 5, 5, 5.2, 5.2, 5, 5, 5, 5, 5, 5, 5]
AREA_BEATS = {1: (1, 7), 2: (8, 13), 3: (14, 19), 4: (20, 25), 5: (26, 30), 6: (31, 35)}
AREA_COLORS = {1: "#2a7ae2", 2: "#ee5a24", 3: "#10ac84", 4: "#f0a500", 5: "#e8779a", 6: "#1e8a2e"}
RED, BLUE, GREY = "#d62728", "#1f5fa8", "#c9c9c9"

plt.rcParams.update({
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e6e6e6",
    "axes.titlelocation": "left", "axes.titlesize": 12,
    "xtick.labelsize": 9, "ytick.labelsize": 9,
})


def hour_label(h):
    return "12am" if h == 0 else "12pm" if h == 12 else f"{h}am" if h < 12 else f"{h - 12}pm"


def headline(fig, title, subtitle):
    h = fig.get_figheight()
    top = max(ax.get_position().y1 for ax in fig.axes) + 0.35 / h  # leave room for panel titles
    fig.suptitle(title, x=0.01, y=top + 0.7 / h, ha="left", fontsize=16, fontweight="bold")
    fig.text(0.01, top + 0.3 / h, subtitle, ha="left", fontsize=11, color="#444")


def save(fig, name):
    path = OUT / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


# --- Data ---------------------------------------------------------------------------------

def load_hourly_2024():
    a = pd.read_csv(DATA / "2024_answer_time.csv", skiprows=1).iloc[:24].apply(pd.to_numeric, errors="coerce")
    return pd.DataFrame({
        "hour": a["Hour of Day"].astype(int),
        "calls_hr": a["Total Calls"] / DAYS_2024,
        "answer_s": a["Answer Time (s)"],
        "min_staff": AUDIT_MIN_STAFF,
    }).assign(calls_per_staff=lambda d: d.calls_hr / d.min_staff)


def load_monthly_2024():
    xls = pd.read_excel(DATA / "911_01Jan-21Jun2024_OPD_Average Call Duration.xls", sheet_name=None, header=None)
    rows = []
    for sheet, days in MONTH_DAYS.items():
        m = xls[sheet].iloc[29:53].copy()
        for col in (3, 6, 7):
            m[col] = pd.to_numeric(m[col], errors="coerce")
        for _, r in m.iterrows():
            rows.append({"month": sheet.replace("2024", "").replace("01-21Jun", "June 1-21"),
                         "hour": pd.Timestamp(r[0]).hour, "calls": r[3], "answer_s": r[6] + r[7]})
    return pd.DataFrame(rows)


# --- Story 1: phone demand vs scheduled call takers -----------------------------------------

def chart_phone_demand_vs_staffing(h):
    r = np.corrcoef(h.calls_per_staff, h.answer_s)[0, 1]
    fig = plt.figure(figsize=(17, 8.5))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.9, 1], height_ratios=[1, 1], hspace=0.35, wspace=0.18)
    a_top, a_bot, a_sc = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[1, 0]), fig.add_subplot(gs[:, 1])
    headline(fig, "911 callers wait 4x the target from 8am–2pm — and answers slow when each call taker has more calls",
             "Average day, Jan 1 – Jun 21 2024 (the only hourly 911 phone data available). "
             f"n = {int(h.calls_hr.sum() * DAYS_2024):,} calls.")

    # top: demand vs scheduled staff
    a_top.bar(h.hour, h.calls_hr, color=GREY, width=0.75, label="911 calls per hour")
    a_top.set_ylabel("911 calls per hour")
    a_top.set_ylim(0, 70)
    ax2 = a_top.twinx()
    ax2.step(h.hour, h.min_staff, where="mid", color=BLUE, lw=2.5, label="scheduled minimum call takers")
    ax2.set_ylim(0, 7)
    ax2.set_ylabel("scheduled call takers", color=BLUE)
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    a_top.set_title("Demand vs. scheduled 911 call takers")
    a_top.text(-0.3, 57, "Most call takers,\nfewest calls", fontsize=9, color=BLUE)
    a_top.text(4.4, 57, "Fewest call takers (2.5)\nas calls rise", fontsize=9, color=BLUE)
    handles = a_top.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    a_top.legend(handles, ["911 calls per hour", "scheduled minimum call takers (City Auditor est.)"],
                 loc="upper right", fontsize=8, frameon=False)

    # bottom: answer time
    a_bot.plot(h.hour, h.answer_s, "o-", color=RED, lw=2.5)
    a_bot.axhline(15, ls="--", color="k", lw=1)
    a_bot.text(-0.4, 17, "15 s target", fontsize=8)
    a_bot.fill_between(h.hour, 15, h.answer_s, where=h.answer_s > 15, color=RED, alpha=0.08)
    worst, best = h.loc[h.answer_s.idxmax()], h.loc[h.answer_s.idxmin()]
    a_bot.annotate(f"{hour_label(int(worst.hour))}: {worst.answer_s:.0f} s", (worst.hour, worst.answer_s),
                   xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9, color=RED, fontweight="bold")
    a_bot.annotate(f"{hour_label(int(best.hour))}: {best.answer_s:.0f} s", (best.hour, best.answer_s),
                   xytext=(0, -16), textcoords="offset points", ha="center", fontsize=9, color=RED)
    a_bot.set_ylim(0, 80)
    a_bot.set_ylabel("average answer time (s)")
    a_bot.set_title("Average time to answer a 911 call")
    for ax in (a_top, a_bot):
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([hour_label(x) for x in range(0, 24, 2)])
        ax.set_xlim(-0.6, 23.6)

    # right: calls per scheduled call taker vs answer time
    a_sc.scatter(h.calls_per_staff, h.answer_s, s=70, color=RED, edgecolor="k", zorder=3)
    for _, row in h.iterrows():
        a_sc.annotate(hour_label(int(row.hour)), (row.calls_per_staff, row.answer_s), xytext=(5, 3),
                      textcoords="offset points", fontsize=7.5, color="#444")
    m, b = np.polyfit(h.calls_per_staff, h.answer_s, 1)
    xs = np.linspace(h.calls_per_staff.min(), h.calls_per_staff.max(), 10)
    a_sc.plot(xs, m * xs + b, color="#999", ls="--", lw=1)
    a_sc.set_xlabel("911 calls per hour, per scheduled call taker")
    a_sc.set_ylabel("average answer time (s)")
    a_sc.set_ylim(0, 80)
    a_sc.set_title(f"Hours with more calls per call taker tend to answer slower (r = {r:.2f})")

    fig.text(0.01, -0.03,
             "Sources: OPD 911 phone data by hour, Jan 1 – Jun 21 2024 (2024_answer_time.csv, public records request 24-6237). "
             "Scheduled call takers: City Auditor 911 audit (Oct 2025), Exhibit 19,\nestimated minimum staffing for 911 call takers "
             "(2023 schedule, read off the published chart). Answer time = time in queue + ring time.",
             fontsize=8, color="#555")
    return save(fig, "story_1_phone_demand_vs_staffing_2024.png"), r


# --- Story 2: answer time by month x hour -----------------------------------------------------

def chart_answer_heatmap(m):
    months = list(dict.fromkeys(m.month))
    grid = m.pivot(index="month", columns="hour", values="answer_s").loc[months]
    fig, ax = plt.subplots(figsize=(17, 5))
    headline(fig, "The midday slowdown isn't a fluke — it happens every month",
             "Average seconds to answer a 911 call, by month and hour, Jan 1 – Jun 21 2024. Darker = slower.")
    im = ax.imshow(grid.values, aspect="auto", cmap="Reds", vmin=0, vmax=np.nanmax(grid.values))
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            v = grid.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8, color="white" if v > 55 else "#333")
    ax.set_xticks(range(24))
    ax.set_xticklabels([hour_label(x) for x in range(24)], fontsize=8)
    ax.set_yticks(range(len(months)))
    ax.set_yticklabels(months)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01, label="seconds to answer (target: 15)")
    fig.text(0.01, -0.06,
             f"n = {int(m.calls.sum()):,} 911 calls. Source: 911_01Jan-21Jun2024_OPD_Average Call Duration.xls "
             "(OPD, public records request 24-6237). Answer time = time in queue + ring time.",
             fontsize=8, color="#555")
    return save(fig, "story_2_answer_time_by_month_hour_2024.png")


# --- Story 5: Area demand vs officers --------------------------------------------------------

def beat_to_area(beat):
    digits = "".join(ch for ch in str(beat) if ch.isdigit())
    if not digits:
        return np.nan
    n = int(digits)
    return next((a for a, (lo, hi) in AREA_BEATS.items() if lo <= n <= hi), np.nan)


def officers_assigned_2025():
    """Average patrol officers assigned per Area x hour across 2025 (overnight shifts carry into the next day)."""
    s = pd.read_csv(OPD / "Outputs/opd_patrol_officers_by_shift_day.csv", parse_dates=["valid_from", "valid_to"])
    days = pd.date_range("2025-01-01", "2025-12-31")
    total = np.zeros((7, 24))
    for day in days:
        for d_, offset in ((day, 0), (day - pd.Timedelta(days=1), -24)):
            rows = s[(s.valid_from <= d_) & (s.valid_to >= d_) & (s.day == d_.day_name())]
            for _, r in rows.iterrows():
                start, end = int(r.shift_start[:2]), int(r.shift_end[:2])
                for hh in range(start + offset, start + ((end - start) % 24 or 24) + offset):
                    if 0 <= hh < 24:
                        total[r.area, hh] += r.officers_assigned
    return pd.DataFrame(total[1:] / len(days), index=range(1, 7))


def chart_area_demand():
    d = pd.read_parquet(DATA / "harmonized_calls_2021_2026.parquet", columns=["event_number", "beat", "call_source", "event_time"])
    d = d[(d.event_time.dt.year == 2025) & d.call_source.isin(["911", "Phone"])].drop_duplicates("event_number")
    d["area"] = d.beat.map(beat_to_area)
    d["hour"] = d.event_time.dt.hour
    calls = d.dropna(subset=["area"]).groupby(["area", "hour"]).size().unstack(fill_value=0) / 365
    officers = officers_assigned_2025()
    ratio = calls / officers.values

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(18, 6.5))
    headline(fig, "Patrol officers are most stretched from 4–9pm — in the gap between day and night shifts",
             "Calls from the public by Patrol Area, 2025, compared with officers assigned on shift at each hour.")
    for area, color in AREA_COLORS.items():
        lo, hi = AREA_BEATS[area]
        a1.plot(calls.columns, calls.loc[area], "o-", ms=3, lw=2, color=color,
                label=f"Area {area} · beats {lo}–{hi} ({int(calls.loc[area].sum() * 365):,} calls)")
        a2.plot(ratio.columns, ratio.loc[area], "o-", ms=3, lw=2, color=color, label=f"Area {area}")
    a2.axvspan(16, 21, color="#f6d5d5", alpha=0.5, zorder=0)
    a2.text(18.5, 0.12, "day shift has left,\nnight shift not yet on", fontsize=9, color=RED, ha="center")
    for ax in (a1, a2):
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([hour_label(x) for x in range(0, 24, 2)])
        ax.set_xlabel("hour call received")
    a1.set_ylabel("average calls per hour")
    a1.set_title("Calls per hour — Area 1 (downtown) is busiest all day")
    a1.legend(fontsize=8, frameon=False)
    a2.set_ylabel("calls per hour ÷ officers assigned on shift")
    a2.set_title("Calls per officer on shift — dips where two shifts overlap")
    a2.legend(fontsize=8, frameon=False, ncol=2, loc="upper left")
    fig.text(0.01, -0.04,
             f"n = {int(calls.values.sum() * 365):,} public calls (911 + phone; officer-initiated excluded; deduplicated). "
             "Officers = permanent patrol assignments per shift from OPD staffing reports (opd_patrol_officers_by_shift_day.csv);\n"
             "these include officers on leave, so actual officers on duty are lower. Sources: harmonized_calls_2021_2026.parquet, "
             "opd_patrol_officers_by_shift_day.csv.",
             fontsize=8, color="#555")
    return save(fig, "story_5_calls_per_officer_by_area_2025.png"), ratio


if __name__ == "__main__":
    h = load_hourly_2024()
    p, r = chart_phone_demand_vs_staffing(h)
    print(p, f"r = {r:.2f}")
    print(h.round(2).to_string(index=False))
    print(chart_answer_heatmap(load_monthly_2024()))
    p, ratio = chart_area_demand()
    print(p)
    print(ratio.round(2).to_string())
