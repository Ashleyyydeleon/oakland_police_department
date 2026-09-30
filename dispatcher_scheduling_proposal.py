"""OPD 911 call-taker scheduling proposal: forecast -> Erlang C -> required vs current -> shift plan.

WHAT   How many 911 call takers OPD needs each hour to answer 90% of 911 calls within 15 s (CalOES standard),
       compared with OPD's current minimum staffing, plus a 10-hour shift plan that closes the gap.
DEMAND Anton's hourly forecast (oakland_911_forecast.ipynb, NB GLM, final feature set), back-test
       Jul 2025 - Jun 2026, issued 48-71 h ahead. cache/bt_glm_a36ba550a4.pkl. We plan on the P90
       (covers 9 of 10 hours). Converted from CAD public calls to 911-line calls with the hourly ratio
       observed Jan-Jun 2024 (2024_answer_time.csv vs cache/hourly_calls.parquet; overall 0.99).
AHT    Talk time 116 s = San Francisco 2023 (City Auditor audit, Exhibit 49, ECaTS). Oakland's own
       2024 talk+hold is 112 s, so the proxy is close.
MATH   Erlang C: smallest N with P(wait <= 15 s) >= 90% at the hour's call volume and AHT.
CURRENT City Auditor audit, Exhibit 19: estimated minimum 911 call takers by hour (2023 schedule).
OFFICERS opd_patrol_officers_by_shift_day.csv (OPD staffing reports / 2023 watch-schedule memo), first and last
       hour of each shift excluded (line-up / paperwork).

Two scenarios (assumptions to replace with OPD data when it arrives):
  FLOOR     AHT 116 s, no after-call work, staff answer 100% of their shift.
  PLANNING  AHT 116 s + 30 s after-call work (CAD entry before the next call), 30% shrinkage
            (breaks, meals, training, leave; typical contact-center range 25-35%).

Writes charts to OUT (default ./outputs/dispatcher; pass --box for Box Outputs).
"""
import glob
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import TwoSlopeNorm
from scipy.optimize import Bounds, LinearConstraint, milp

try:
    from box_utils import BOX_ROOT
except ImportError:
    BOX_ROOT = Path(glob.glob(str(Path.home() / "Library/CloudStorage/Box-*"))[0])

OPD = BOX_ROOT / "OPD & TAN - Core Workspace" / "02 Oakland Police Dept (OPD)"
DATA = OPD / "Data/Our Data"
OUT = OPD / "Outputs" if "--box" in sys.argv else Path("outputs/dispatcher")
OUT.mkdir(exist_ok=True)
TZ = "America/Los_Angeles"

TARGET_S, TARGET_PCT = 15, 0.90
TALK_S = 116                     # SF 2023 talk time (audit Exhibit 49)
SCENARIOS = {"floor": dict(aht=TALK_S, shrink=0.0), "planning": dict(aht=TALK_S + 30, shrink=0.30)}
SHIFT_H = 10                     # OPD dispatchers work 4 x 10-hour shifts (audit p.29)
FTE_HOURS_WEEK = 40
EXHIBIT_19 = np.array([5, 5, 5, 3.1, 3.1, 2.5, 2.5, 2.6, 2.6, 4, 4, 5, 5, 5, 5, 5.2, 5.2, 5, 5, 5, 5, 5, 5, 5])
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
RED, BLUE, GREY, GREEN = "#c0392b", "#1f5fa8", "#bdbdbd", "#2e8b57"

plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y",
                     "grid.color": "#e6e6e6", "axes.titlelocation": "left", "axes.titlesize": 12,
                     "xtick.labelsize": 9, "ytick.labelsize": 9})


def hl(h):
    return "12am" if h == 0 else "12pm" if h == 12 else f"{h}am" if h < 12 else f"{h - 12}pm"


# --- Erlang C ------------------------------------------------------------------------------

def service_level(n, calls_hr, aht):
    a = calls_hr * aht / 3600
    if n <= a:
        return 0.0
    head = sum(a ** k / math.factorial(k) for k in range(n))
    tail = a ** n / math.factorial(n) * n / (n - a)
    p_wait = tail / (head + tail)
    return 1 - p_wait * math.exp(-(n - a) * TARGET_S / aht)


def required(calls_hr, aht, shrink):
    n = 1
    while service_level(n, calls_hr, aht) < TARGET_PCT:
        n += 1
    return n / (1 - shrink)  # scheduled staff so that n are actually on the phones


# --- Data -------------------------------------------------------------------------------------

def load_demand():
    f = pd.read_pickle(OPD / "cache/bt_glm_a36ba550a4.pkl")["val"]
    hc = pd.read_parquet(OPD / "cache/hourly_calls.parquet")
    lo, hi = pd.Timestamp("2024-01-01", tz=TZ), pd.Timestamp("2024-06-22", tz=TZ)
    cad24 = hc[(hc.index >= lo) & (hc.index < hi)].calls.groupby(lambda t: t.hour).sum()
    ph = pd.read_csv(DATA / "2024_answer_time.csv", skiprows=1).iloc[:24].apply(pd.to_numeric, errors="coerce")
    ratio = pd.Series(ph["Total Calls"].to_numpy() / cad24.to_numpy(), index=range(24))
    f = f.assign(hour=f.index.hour, dow=f.index.dayofweek)
    f["y_911"] = f.y * f.hour.map(ratio)
    f["p90_911"] = f.q90 * f.hour.map(ratio)
    f["mean_911"] = f.mu * f.hour.map(ratio)
    return f, ratio


def officers_on_patrol(index):
    """Average officers on patrol per hour over the forecast period, excluding the first and last hour of each shift."""
    s = pd.read_csv(OPD / "Outputs/opd_patrol_officers_by_shift_day.csv", parse_dates=["valid_from", "valid_to"])
    days = pd.date_range(index[0].date(), index[-1].date())
    tot = np.zeros(24)
    for day in days:
        for d_, off in ((day, 0), (day - pd.Timedelta(days=1), -24)):
            rows = s[(s.valid_from <= d_) & (s.valid_to >= d_) & (s.day == d_.day_name())]
            for _, r in rows.iterrows():
                a, b = int(r.shift_start[:2]), int(r.shift_end[:2])
                length = (b - a) % 24 or 24
                for h in range(a + 1 + off, a + length - 1 + off):  # drop first and last hour
                    if 0 <= h < 24:
                        tot[h] += r.officers_assigned
    return tot / len(days)


# --- Shift optimisation (10-hour shifts, any start hour) ------------------------------------------

def cover_matrix():
    m = np.zeros((24, 24))
    for s in range(24):
        for k in range(SHIFT_H):
            m[(s + k) % 24, s] = 1
    return m


MAX_STARTS = 5    # keep the roster practical: at most 5 different shift start times
MIN_ON_SHIFT = 3  # never fewer than 3 call takers in any hour (Exhibit 19 minimum is 2.5)


def sl_scheduled(sched, calls_hr, aht, shrink):
    """Share answered within 15 s when `sched` people are scheduled (fractional -> interpolate)."""
    on = sched * (1 - shrink)
    lo = int(math.floor(on))
    frac = on - lo
    s_lo = service_level(lo, calls_hr, aht) if lo >= 1 else 0.0
    return s_lo if frac == 0 else (1 - frac) * s_lo + frac * service_level(lo + 1, calls_hr, aht)


def daily_sl(cov, calls, aht, shrink):
    return float(np.average([sl_scheduled(c, v, aht, shrink) for c, v in zip(cov, calls)], weights=calls))


def plan_full_cover(req):
    """Fewest 10-hour shifts (at most MAX_STARTS start times) so every hour meets the requirement."""
    A = cover_matrix()
    c = np.r_[np.ones(24), np.zeros(24)]                        # x = shifts per start, y = start used (0/1)
    cov = LinearConstraint(np.c_[A, np.zeros((24, 24))], lb=np.ceil(req - 1e-9), ub=np.inf)
    link = LinearConstraint(np.c_[np.eye(24), -30 * np.eye(24)], lb=-np.inf, ub=0)
    starts = LinearConstraint(np.r_[np.zeros(24), np.ones(24)][None, :], lb=0, ub=MAX_STARTS)
    res = milp(c, constraints=[cov, link, starts], integrality=np.ones(48),
               bounds=Bounds(np.zeros(48), np.r_[np.full(24, np.inf), np.ones(24)]))
    return np.round(res.x[:24]).astype(int)


def plan_same_hours(n_shifts, req, calls, aht, shrink):
    """Re-time n_shifts x 10 h (no new hires): integer program minimising call-weighted shortfall vs the
    requirement (at most MAX_STARTS start times), then single-shift moves while they raise the share within 15 s."""
    A = cover_matrix()
    w = calls / calls.sum()
    c = np.r_[np.zeros(24), np.zeros(24), w]                          # x, y, u
    Z = np.zeros((24, 24))
    cov = LinearConstraint(np.c_[A, Z, np.eye(24)], lb=req, ub=np.inf)
    link = LinearConstraint(np.c_[np.eye(24), -30 * np.eye(24), Z], lb=-np.inf, ub=0)
    starts = LinearConstraint(np.r_[np.zeros(24), np.ones(24), np.zeros(24)][None, :], lb=0, ub=MAX_STARTS)
    total = LinearConstraint(np.r_[np.ones(24), np.zeros(48)][None, :], lb=n_shifts, ub=n_shifts)
    floor_ = LinearConstraint(np.c_[A, Z, Z], lb=MIN_ON_SHIFT, ub=np.inf)
    res = milp(c, constraints=[cov, link, starts, total, floor_], integrality=np.r_[np.ones(48), np.zeros(24)],
               bounds=Bounds(np.zeros(72), np.r_[np.full(24, np.inf), np.ones(24), np.full(24, np.inf)]))
    x = np.round(res.x[:24]).astype(int)
    score = lambda v: daily_sl(A @ v, calls, aht, shrink)
    improved = True
    while improved:
        improved = False
        for a in np.flatnonzero(x):
            for b in range(24):
                y = x.copy(); y[a] -= 1; y[b] += 1
                if np.count_nonzero(y) <= MAX_STARTS and (A @ y).min() >= MIN_ON_SHIFT and score(y) > score(x) + 1e-9:
                    x, improved = y, True
                    break
            if improved:
                break
    return x


def describe(x):
    return [(hl(s), hl((s + SHIFT_H) % 24), int(n)) for s, n in enumerate(x) if n > 0]


# --- Charts ---------------------------------------------------------------------------------------

def headline(fig, title, sub):
    h = fig.get_figheight()
    top = max(ax.get_position().y1 for ax in fig.axes) + 0.35 / h
    fig.suptitle(title, x=0.01, y=top + 0.7 / h, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.01, top + 0.3 / h, sub, ha="left", fontsize=10.5, color="#444")


def save(fig, name):
    p = OUT / name
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return p


def xticks(ax):
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([hl(h) for h in range(0, 24, 2)])
    ax.set_xlim(-0.6, 23.6)


def chart_required_vs_current(hr, officers):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(14, 9.5), gridspec_kw={"height_ratios": [1.5, 1], "hspace": 0.4})
    a1.bar(hr.index, EXHIBIT_19, color=GREY, width=0.75, label="Current: OPD minimum 911 call takers (Exhibit 19)")
    a1.step(hr.index, hr.req_floor, where="mid", color=BLUE, lw=2.2, ls="--", label="Required, floor (116 s calls, no breaks)")
    a1.step(hr.index, hr.req_plan, where="mid", color=RED, lw=2.8, label="Required, planning (+30 s wrap-up, 30% breaks/leave)")
    a1.fill_between(hr.index, EXHIBIT_19, hr.req_plan, where=hr.req_plan > EXHIBIT_19, step="mid", color=RED, alpha=0.12)
    worst = hr.gap_plan.idxmax()
    a1.annotate(f"Largest gap: {hl(worst)}\n+{hr.gap_plan[worst]:.1f} call takers", (worst, hr.req_plan[worst]),
                xytext=(worst + 3.2, 1.2), fontsize=9.5, color=RED, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=RED))
    a1.set_ylim(0, hr.req_plan.max() + 3)
    a1.set_ylabel("911 call takers on shift")
    a1.set_title("A. 911 call takers: required to answer 90% within 15 s vs. current minimum")
    a1.legend(loc="upper left", fontsize=8.5, frameon=False)
    ax2 = a1.twinx()
    ax2.plot(hr.index, hr.p90_911, color="#666", lw=1.2, ls=":")
    ax2.set_ylabel("forecast 911 calls/hour (P90, dotted)", color="#666")
    ax2.set_ylim(0, hr.p90_911.max() * 1.6)
    ax2.grid(False)
    ax2.spines["right"].set_visible(True)
    xticks(a1)

    a2.bar(range(24), officers, color="#9fb7d9", width=0.75, label="Patrol officers on patrol (assigned, minus first/last shift hour)")
    a2.set_ylabel("officers on patrol")
    ax3 = a2.twinx()
    ax3.plot(hr.index, hr.mean_911, color="k", lw=1.8, label="forecast calls/hour (mean)")
    ax3.set_ylabel("forecast calls/hour (line)")
    ax3.grid(False)
    ax3.spines["right"].set_visible(True)
    ax3.set_ylim(0, hr.mean_911.max() * 1.3)
    a2.set_title("B. Officers on patrol vs. calls: dips at 6-7am, 2-3pm and 9-10pm are shift changes (line-up/paperwork)")
    h1, l1 = a2.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    a2.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8.5, frameon=False)
    xticks(a2)
    headline(fig, "OPD's minimum is 2–3 call takers short of the 90%/15 s standard at most hours — worst 6–10am",
             "Average day, Jul 2025 – Jun 2026 forecast (Anton's model, P90). Erlang C, CalOES standard: 90% of 911 calls answered within 15 s.")
    fig.text(0.01, 0.01, "Sources: forecast cache/bt_glm_a36ba550a4.pkl; 911-line conversion from 2024_answer_time.csv; talk time = San Francisco 2023 (audit Exhibit 49); "
             "current = audit Exhibit 19; officers = opd_patrol_officers_by_shift_day.csv.", fontsize=7.5, color="#555")
    return save(fig, "sched_1_required_vs_current.png")


def chart_heatmap(gap):
    fig, ax = plt.subplots(figsize=(15, 4.6))
    lim = max(abs(np.nanmin(gap.values)), np.nanmax(gap.values))
    im = ax.imshow(gap.values, aspect="auto", cmap="RdBu_r", norm=TwoSlopeNorm(0, -lim, lim))
    for i in range(gap.shape[0]):
        for j in range(gap.shape[1]):
            v = gap.values[i, j]
            ax.text(j, i, f"{v:+.0f}" if abs(v) >= 0.5 else "0", ha="center", va="center", fontsize=8,
                    color="white" if abs(v) > lim * 0.6 else "#222")
    ax.set_xticks(range(24))
    ax.set_xticklabels([hl(h) for h in range(24)], fontsize=8)
    ax.set_yticks(range(7))
    ax.set_yticklabels(DAYS)
    ax.grid(False)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01, label="call takers short (+) / spare (−)")
    headline(fig, "Where the gaps are: red = understaffed, blue = more than needed",
             "Required (planning scenario) minus current minimum, by weekday and hour. Forecast P90, Jul 2025 – Jun 2026.")
    fig.text(0.01, -0.02, "Current minimum (Exhibit 19) is the same every day; required varies by day from the forecast. "
             "Planning = 116 s talk + 30 s wrap-up, 30% shrinkage.", fontsize=7.5, color="#555")
    return save(fig, "sched_2_gap_heatmap.png")


def chart_shift_plan(hr, plans):
    A = cover_matrix()
    fig, axes = plt.subplots(len(plans), 1, figsize=(14, 4.6 * len(plans)), gridspec_kw={"hspace": 0.55})
    for ax, (label, p) in zip(axes, plans.items()):
        cov = A @ p["x"]
        ax.bar(range(24), cov, color="#9fd3b0", width=0.75, label="proposed call takers on shift")
        ax.step(range(24), EXHIBIT_19, where="mid", color="#555", lw=1.8, ls="--", label="current minimum (Exhibit 19)")
        ax.step(range(24), hr.req_plan, where="mid", color=RED, lw=2.2, label="needed for 90% in that hour")
        starts = "   ".join(f"{a}–{b}: {n}" for a, b, n in describe(p["x"]))
        ax.set_title(f"{label}:  {p['x'].sum()} shifts/day · +{p['fte']:.1f} FTE · est. answered ≤15 s {p['sl'] * 100:.0f}% (today {p['today'] * 100:.0f}%)\n"
                     f"Shift starts (10 h each, people per day): {starts}", fontsize=11)
        ax.set_ylim(0, hr.req_plan.max() + 3.5)
        ax.set_ylabel("call takers on shift")
        ax.legend(loc="upper left", fontsize=8.5, frameon=False)
        xticks(ax)
    headline(fig, "Shift proposal: add daytime and evening shifts starting 4am, 8am, 2pm and 6pm",
             "Optimised 10-hour shift starts (≤5 start times, never fewer than 3 call takers) for the average day, planning scenario.")
    fig.text(0.01, 0.01, "FTE = added call-taker hours/day × 7 ÷ 40. Answer rates are Erlang C estimates on the forecast mean with 30% shrinkage and 146 s handling time; "
             "the same assumptions give 77% for today's schedule vs 73–79% actually measured Jan–Jul 2026.", fontsize=7.5, color="#555")
    return save(fig, "sched_3_shift_proposal.png")


def chart_forecast_shape(f):
    """Anton's forecast: the shape of the day (weekday vs weekend) with the P50-P90 band."""
    wk = f.assign(we=f.dow >= 5)
    fig, ax = plt.subplots(figsize=(13, 5.2))
    wd = wk[~wk.we].groupby("hour")[["mean_911", "p90_911"]].mean()
    we = wk[wk.we].groupby("hour")[["mean_911", "p90_911"]].mean()
    ax.fill_between(wd.index, wd.mean_911, wd.p90_911, color=BLUE, alpha=0.15, label="Weekday: typical to busy (P90) hour")
    ax.plot(wd.index, wd.mean_911, color=BLUE, lw=2.8, label="Weekday, typical (forecast mean)")
    ax.plot(we.index, we.mean_911, color="#e08a1e", lw=2.8, ls="--", label="Weekend, typical (forecast mean)")
    lo, hi = wd.mean_911.idxmin(), wd.mean_911.idxmax()
    ax.annotate(f"Quietest: {hl(lo)}\n~{wd.mean_911[lo]:.0f} calls/hr", (lo, wd.mean_911[lo]), (lo + 0.6, wd.mean_911[lo] - 13),
                arrowprops=dict(arrowstyle="-", color="#444"), fontsize=10, color="#222")
    ax.annotate(f"Busiest: {hl(hi)}\n~{wd.mean_911[hi]:.0f} calls/hr\n({wd.mean_911[hi] / wd.mean_911[lo]:.1f}x the quietest)", (hi, wd.mean_911[hi]),
                (hi - 4.5, wd.mean_911[hi] + 14), arrowprops=dict(arrowstyle="-", color="#444"), fontsize=10, color="#222")
    ax.annotate("Weekends start the day later:\nbusier after midnight,\nquieter at 7am", (1, we.mean_911[1]), (4.4, 38),
                arrowprops=dict(arrowstyle="-", color="#e08a1e"), fontsize=10, color="#b36a10")
    xticks(ax)
    ax.set_ylim(0, 85)
    ax.set_ylabel("911-line calls per hour")
    ax.legend(loc="upper left", frameon=False, fontsize=9.5)
    ax.set_title("The phones follow a curve, and it is the same every week")
    fig.text(0.01, -0.02, "Anton's hourly forecast, Jul 2025 to Jun 2026, issued 48 to 71 hours ahead; converted to 911-line calls. "
             "His P90 held in 91.5% of the 8,756 hours tested.", fontsize=8, color="#555")
    return save(fig, "sched_0_forecast_shape.png")


def shift_stats(f, x):
    """Per proposed shift: people, hours, calls in the shift window and the quiet-to-busy day range (actual calls, 911-line)."""
    y = f.dropna(subset=["y"]).y_911
    roll = y.rolling(SHIFT_H).sum().shift(-(SHIFT_H - 1))
    rows = []
    for h in range(24):
        if x[h] > 0:
            sums = roll[roll.index.hour == h].dropna()
            lo, mid, hi = sums.quantile([0.1, 0.5, 0.9])
            rows.append(dict(start=h, people=int(x[h]), lo=lo, mid=mid, hi=hi))
    return pd.DataFrame(rows)


def chart_shift_blocks(f, x, label):
    """Proposed call takers stacked by shift, on top of Anton's call curve."""
    hr = f.groupby("hour").mean_911.mean()
    starts = [h for h in range(24) if x[h] > 0]
    pal = ["#2e8b57", "#6fbf8b", "#9fd3b0", "#c7e6d1", "#e3f2e8"]
    fig, ax = plt.subplots(figsize=(13, 5.6))
    bottom = np.zeros(24)
    for i, h in enumerate(starts):
        cov = np.array([x[h] if (hh - h) % 24 < SHIFT_H else 0 for hh in range(24)], dtype=float)
        ax.bar(range(24), cov, bottom=bottom, color=pal[i % len(pal)], edgecolor="white", width=0.9,
               label=f"{int(x[h])} start {hl(h)} (to {hl((h + SHIFT_H) % 24)})")
        bottom += cov
    ax.plot(range(24), EXHIBIT_19, color="#444", lw=2, ls="--", drawstyle="steps-mid", label="Today's minimum")
    ax.set_ylabel("call takers on shift")
    ax.set_ylim(0, 8.4)
    ax2 = ax.twinx()
    ax2.plot(range(24), hr.values, color=BLUE, lw=3, label="Calls per hour (Anton, typical day)")
    ax2.set_ylim(0, 63)
    ax2.set_ylabel("911-line calls per hour", color=BLUE)
    ax2.spines["right"].set_visible(True)
    ax2.grid(False)
    xticks(ax)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", ncol=2, frameon=False, fontsize=9)
    ax.set_title(label)
    return save(fig, "sched_4_shift_blocks.png")


# --- Main ---------------------------------------------------------------------------------------------

def main():
    f, ratio = load_demand()
    hr = f.groupby("hour")[["p90_911", "mean_911"]].mean()
    for name, sc in SCENARIOS.items():
        hr[f"req_{'floor' if name == 'floor' else 'plan'}"] = [required(v, sc["aht"], sc["shrink"]) for v in hr.p90_911]
    hr["current"] = EXHIBIT_19
    hr["gap_plan"] = hr.req_plan - EXHIBIT_19
    hr["gap_floor"] = hr.req_floor - EXHIBIT_19
    cell = f.groupby(["dow", "hour"]).p90_911.mean().unstack()
    sc = SCENARIOS["planning"]
    gap = cell.apply(lambda row: pd.Series([required(v, sc["aht"], sc["shrink"]) for v in row], index=row.index)) - EXHIBIT_19
    gap.index = DAYS
    officers = officers_on_patrol(f.index)

    current_hours = EXHIBIT_19.sum()
    A = cover_matrix()
    calls = hr.mean_911.to_numpy()
    today = daily_sl(EXHIBIT_19, calls, sc["aht"], sc["shrink"])
    options = {}
    for key, n, label in (("A", 11, "Option A — re-time + ~1 hire"),
                          ("B", 13, "Option B — meet the 90% standard for the day"),
                          ("C", 16, "Option C — 90%+ in nearly every hour")):
        x = plan_same_hours(n, hr.req_plan.to_numpy(), calls, sc["aht"], sc["shrink"])
        per = [sl_scheduled(c, v, sc["aht"], sc["shrink"]) for c, v in zip(A @ x, calls)]
        options[key] = dict(label=label, x=x, sl=daily_sl(A @ x, calls, sc["aht"], sc["shrink"]), worst=min(per),
                            fte=(n * SHIFT_H - current_hours) * 7 / FTE_HOURS_WEEK, today=today)
    print(hr.round(2).to_string())
    print("\nofficers on patrol by hour:", np.round(officers, 0).astype(int).tolist())
    print(f"today: {current_hours:.1f} call-taker hours/day, est. {today:.1%} within 15 s")
    for k, o in options.items():
        print(k, o["label"], describe(o["x"]), f"+{o['fte']:.1f} FTE  SL {o['sl']:.1%}  worst hour {o['worst']:.0%}  cov {(A @ o['x']).astype(int).tolist()}")
    print(chart_required_vs_current(hr, officers))
    print(chart_heatmap(gap))
    print(chart_shift_plan(hr, {options[k]["label"]: options[k] for k in ("B", "C")}))
    print(chart_forecast_shape(f))
    print(chart_shift_blocks(f, options["B"]["x"], "Option B: shifts stacked to follow the call curve"))
    print(shift_stats(f, options["B"]["x"]).round(0).to_string())
    return hr, gap, options, officers, today


if __name__ == "__main__":
    main()
