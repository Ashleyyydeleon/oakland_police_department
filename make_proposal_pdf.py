"""Build the dispatcher scheduling proposal PDF (selectable text)."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

F = Path("/System/Library/Fonts/Supplemental")
for n, f in (("Arial", "Arial.ttf"), ("Arial-Bold", "Arial Bold.ttf"), ("Arial-Italic", "Arial Italic.ttf")):
    pdfmetrics.registerFont(TTFont(n, str(F / f)))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic")

IMG = Path("outputs/dispatcher")
NAVY, GREY, RED, GREEN = colors.HexColor("#1f3a5f"), colors.HexColor("#555555"), colors.HexColor("#b3261e"), colors.HexColor("#2e7d4f")
LIGHT = colors.HexColor("#eef3f9")
base = dict(fontName="Arial", fontSize=9.5, leading=12.5)
S = {
    "title": ParagraphStyle("t", **{**base, "fontName": "Arial-Bold", "fontSize": 18, "leading": 22, "textColor": NAVY}),
    "sub": ParagraphStyle("s", **{**base, "textColor": GREY}),
    "h1": ParagraphStyle("h", **{**base, "fontName": "Arial-Bold", "fontSize": 12.5, "leading": 16, "textColor": NAVY, "spaceBefore": 9, "spaceAfter": 4}),
    "body": ParagraphStyle("b", **base, spaceAfter=3),
    "cell": ParagraphStyle("c", **{**base, "fontSize": 8.8, "leading": 11.2}),
    "cellb": ParagraphStyle("cb", **{**base, "fontName": "Arial-Bold", "fontSize": 8.8, "leading": 11.2}),
    "big": ParagraphStyle("g", **{**base, "fontSize": 11.5, "leading": 15.5}),
    "small": ParagraphStyle("sm", **{**base, "fontSize": 8, "leading": 10, "textColor": GREY}),
}
p = lambda t, s="body": Paragraph(t, S[s])


def table(rows, widths, header=True, shade=None):
    data = [[p(c, "cellb" if (header and i == 0) or j == 0 else "cell") for j, c in enumerate(r)] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * inch for w in widths])
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), LIGHT))
    for r in shade or []:
        st.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#e8f5ec")))
    t.setStyle(TableStyle(st))
    return t


def img(name, width=7.0):
    i = Image(str(IMG / name))
    i.drawWidth, i.drawHeight = width * inch, width * inch * i.imageHeight / i.imageWidth
    return i

summary = Table([[p(
    "<b>The answer.</b> Anton's forecast shows 911 calls follow the same curve every week: quiet at 4am, nearly double by 9am, flat and busy until 9pm. "
    "OPD's schedule doesn't follow that curve. Moving shift starts to <b>4am, 8am, 12pm, 2pm and 6pm</b> and running <b>13 ten-hour call-taker shifts a day instead of ~10.5</b> "
    "(about <b>+4 to 5 full-time call takers</b>) gets OPD from <b>77% to about 91%</b> of 911 calls answered within 15 seconds (the state standard is 90%). "
    "That fits inside OPD's <b>12 open dispatcher positions</b>.", "big")]],
    colWidths=[7.0 * inch])
summary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf1ef")), ("BOX", (0, 0), (-1, -1), 1, RED),
                             ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))

story = [
    p("When to put call takers on the phones", "title"),
    p("A 911 call-taker scheduling proposal built on Anton's call-volume forecast · Oakland Police Department · PITC Fall 2026 · Draft for team review", "sub"),
    Spacer(1, 8), summary,

    p("1. The problem: callers are waiting", "h1"),
    p("California's standard is that <b>90% of 911 calls are answered within 15 seconds</b>. OPD answered <b>54%</b> in 2024 and <b>73 to 79%</b> in Jan to Jul 2026, "
      "below the standard in every month. Every call past 15 seconds is a caller listening to ringing in an emergency. "
      "The question for this proposal: <b>how many call takers, starting when, closes that gap?</b>"),

    p("2. What Anton's forecast tells us: the day has a shape", "h1"),
    p("Anton's model forecasts 911 calls for every hour of the year, issued 48 to 71 hours ahead, which is the window in which shifts can still be changed. "
      "Four things in it drive the schedule:"),
    p("• <b>The curve is steep.</b> Calls bottom out at about 4am (~17 an hour) and peak around 5pm (~49 an hour), <b>2.9 times</b> as many.<br/>"
      "• <b>The morning climb is fast.</b> Weekday volume nearly doubles between 6am and 9am, so people must already be at their desks before it starts.<br/>"
      "• <b>Weekends run on a different clock.</b> About 10 more calls an hour at 1am and 7 fewer at 7am than on weekdays, although total daily volume is the same (~880 calls).<br/>"
      "• <b>The forecast is trustworthy.</b> Across the 8,756 hours tested (Jul 2025 to Jun 2026), his P90 (the level 9 of 10 hours stay under) held <b>91.5%</b> of the time. "
      "We plan on the P90, because an unanswered call costs far more than an idle seat."),
    KeepTogether([img("sched_0_forecast_shape.png", 6.7)]),
    p("<b>Read it:</b> the blue line is a typical weekday, the shaded band runs up to a busy (P90) hour, and the orange line is a typical weekend.", "small"),

    PageBreak(),
    p("3. Today's schedule doesn't follow the curve", "h1"),
    p("OPD's minimum is about 5 call takers for most of the day, and <b>2.5 to 3 between 4 and 9am</b>, just as calls double. With realistic breaks and after-call work, "
      "the standard needs about <b>5.7 call takers overnight and mornings and 7.1 from 8am on</b>. The biggest gap is at <b>6am, 3.2 call takers short</b>. "
      "That is also the hour officers on patrol drop to about 30 (panel B), so the thinnest hour is thin at both ends of the radio."),
    KeepTogether([img("sched_1_required_vs_current.png", 6.1)]),
    p("<b>Read it:</b> grey bars are today's minimum, the red line is what the standard needs, and the pink area is the gap. Panel B leaves out each patrol shift's first and last hour (line-up and paperwork).", "small"),

    PageBreak(),
    p("4. Why shift timing is the lever", "h1"),
    p("Call takers work <b>4 ten-hour shifts a week</b>, so one hire covers a block of the curve, not a single hour. That makes <b>shift start time</b> as important as headcount. "
      "Re-timing today's shifts alone (Option A) lifts the answer rate only from 77% to 81%. Reaching the standard takes both: more shifts, placed where Anton's curve is steepest."),
    table([
        ["Option", "Call-taker shifts/day", "Added full-time call takers", "Est. answered ≤15 s", "Worst hour", "Shift starts (people per day)"],
        ["Today (Exhibit 19)", "~10.5", "—", "77% (actual 2026: 73–79%)", "—", "Current minimum schedule"],
        ["A. Re-time + ~1 hire", "11", "+0.9", "81%", "65%", "2am ×2, 6am ×3, 12pm ×2, 4pm ×3, 8pm ×1"],
        ["<b>B. Meet the standard</b>", "<b>13</b>", "<b>+4.4</b>", "<b>91%</b>", "62%", "<b>4am ×4, 8am ×2, 12pm ×1, 2pm ×3, 6pm ×3</b>"],
        ["C. 90%+ nearly every hour", "16", "+9.7", "97%", "93%", "4am ×3, 8am ×4, 2pm ×4, 6pm ×3, 10pm ×2"],
    ], [1.3, 0.85, 0.95, 1.2, 0.6, 2.1], shade=[3]),
    p("Every option keeps at least 3 call takers on the phones every hour and uses at most 5 shift start times. Full-time equivalents (FTE) = added call-taker hours per day × 7 ÷ 40.", "small"),
    Spacer(1, 6),
    p("<b>Option B, shift by shift.</b> Follow the curve from left to right:"),
    p("• <b>4am start (4 people)</b> are at full strength before the 6 to 9am climb, when today's schedule is at its thinnest.<br/>"
      "• <b>8am and 12pm starts (3 people)</b> add cover for the morning rise and the midday plateau.<br/>"
      "• <b>2pm start (3 people)</b> takes over as the 4am group leaves, through the evening peak.<br/>"
      "• <b>6pm start (3 people)</b> carries the evening and the quiet night to 4am, then hands over to the 4am group."),
    KeepTogether([img("sched_4_shift_blocks.png", 6.6)]),
    p("<b>Read it:</b> each green layer is one shift start. The blue line is calls per hour; the dashed line is today's minimum.", "small"),

    PageBreak(),
    p("5. Where Anton's forecast keeps the roster honest", "h1"),
    p("A fixed roster is built on a typical day, but days differ. Looking at actual calls over the same year, the same shift can see very different loads:"),
    table([
        ["Shift (10 h)", "People", "Typical calls in the shift", "Quiet day to busy day (10th to 90th percentile)", "Busy-day swing vs typical"],
        ["4am to 2pm", "4", "~327", "291 to 364", "+11%"],
        ["8am to 6pm", "2", "~427", "375 to 473", "+11%"],
        ["12pm to 10pm", "1", "~457", "412 to 498", "+9%"],
        ["2pm to 12am", "3", "~440", "403 to 493", "+12%"],
        ["<b>6pm to 4am</b>", "<b>3</b>", "<b>~351</b>", "<b>306 to 436</b>", "<b>+24%</b>"],
    ], [1.2, 0.6, 1.4, 2.4, 1.4], shade=[5]),
    p("The <b>evening-into-night shift swings most</b>. It is a weekend effect: a 6pm shift sees about <b>400 calls on Fridays and Saturdays versus about 325 Monday to Thursday</b>, and 35 of its 37 busiest days are Fridays or Saturdays. "
      "Because Anton's forecast for any day is available <b>48 to 71 hours ahead</b>, there is still time to act. We propose three layers:", "body"),
    p("<b>Layer 1. A base roster</b> (Option B) built on the typical curve.<br/>"
      "<b>Layer 2. A Friday/Saturday variant</b> with extra evening cover and later starts, since those nights run ~20% hotter and weekends start the day slowly (not yet modeled; next step).<br/>"
      "<b>Layer 3. A two-day-ahead check.</b> Each morning, compare Anton's P90 for the day after tomorrow with the roster. Where the P90 shift load is above what the roster covers, "
      "fill the gap with an overtime or swap request while it can still be arranged."),

    p("6. What we're asking for", "h1"),
    p("<b>Adopt Option B:</b> 13 call-taker shifts a day, starting at 4am, 8am, 12pm, 2pm and 6pm, about <b>+4.4 full-time call takers</b>. Estimated result: <b>91% of 911 calls answered within 15 seconds</b> "
      "on an average day, up from 77%. Option C (+9.7 FTE, 97%) is the route to 90% in nearly every hour, and it also fits within the 12 open positions. "
      "To firm this up we need three things from OPD: after-call work time per call, real breaks and leave, and the actual dispatch-center shift sheets."),

    PageBreak(),
    p("Appendix: how we got there", "h1"),
    table([
        ["Step", "Input", "Source"],
        ["1. Calls per hour", "Anton's forecast, planning on the P90. Converted to 911-line calls with the hourly ratio seen in 2024 (overall 0.99×).",
         "oakland_911_forecast.ipynb, final model back-test (Box: cache/bt_glm_a36ba550a4.pkl); 2024_answer_time.csv"],
        ["2. Time per call", "<b>116 s talk</b>, the San Francisco benchmark. Oakland's own 2024 figure is 112 s, so the proxy is close.",
         "City Auditor 911 audit (Oct 2025), Exhibit 49"],
        ["3. Erlang C", "Smallest number of call takers so that 90% of callers wait 15 s or less at that hour's volume.", "Standard call-center queueing formula"],
        ["4. Current staffing", "OPD's minimum 911 call takers by hour: 2.5 to 5.2.", "Audit Exhibit 19 (2023 schedule, read off the chart)"],
        ["5. Shift plan", "Integer program: best 10-hour shift starts (OPD works 4×10s) for each staffing level.", "dispatcher_scheduling_proposal.py"],
    ], [1.25, 3.4, 2.35]),
    p("Two assumptions Anton asked about", "h1"),
    table([
        ["", ""],
        ["Work after the call<br/>(can't pick up right away)", "Added as <b>+30 s per call</b> of after-call work (CAD entry), so handling time is 146 s instead of 116 s. "
         "This is a placeholder; OPD's CAD entry time would replace it."],
        ["Breaks, bathroom, coffee,<br/>talking to colleagues", "Modeled as <b>30% shrinkage</b>: only 70% of scheduled people are on the phones at any moment (also covers training and leave; "
         "typical contact-center range is 25 to 35%). <b>Check:</b> with these two assumptions, today's schedule comes out at 77%, matching OPD's actual 73 to 79%. "
         "Without them, the model says today's staffing is enough, which the real data shows isn't true."],
    ], [1.7, 5.3], header=False),
    KeepTogether([p("Where the gaps are, by weekday and hour", "h1"), img("sched_2_gap_heatmap.png", 6.0),
                  p("<b>Read it:</b> red = understaffed, blue = more than needed. The gap is widest on weekday mornings, 6 to 10am (+3), and Saturday at 10pm (+4).", "small")]),
    KeepTogether([p("Options B and C compared", "h1"), img("sched_3_shift_proposal.png", 5.4)]),
    p("Limits and next steps", "h1"),
    table([
        ["Limit", "What would fix it"],
        ["After-call work (30 s) and shrinkage (30%) are assumptions.", "OPD data request: CAD entry time per call, and actual breaks and leave."],
        ["Current staffing is the auditor's 2023 minimum, not who actually works each hour.", "OPD data request: dispatch-center shift sheets and roster."],
        ["Covers the 911 line only; call takers also answer 10-digit lines.", "Add the 10-digit line volume and handle time from OPD's phone system."],
        ["Erlang C assumes callers never hang up and calls arrive at random; real waits are burstier.", "The 77% check suggests it's close; re-check against hourly 2025 to 2026 phone data when it arrives."],
        ["The plan is for an average day; a weekend variant and the two-day-ahead trigger are not yet modeled.", "Model weekday and weekend rosters; test how often the P90 check would have fired in the forecast year."],
    ], [3.4, 3.6]),
]

out = IMG / "OPD_911_Call_Taker_Scheduling_Proposal.pdf"
SimpleDocTemplate(str(out), pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.6 * inch,
                  bottomMargin=0.6 * inch, title="When to put call takers on the phones", author="OPD 911 project team").build(story)
print(out.resolve())
