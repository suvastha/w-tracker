# /weighty/services/logic.py
"""
App logic shared by routes:
- BMI + category + color
- Rolling averages (7/30), streaks
- Linear regression projection and ETA toward goal
- Achievements engine
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Tuple
import math

# --- Quotes (20+) ---
QUOTES = [
    "Small steps, big changes.",
    "Consistency is the secret sauce.",
    "You don’t need perfect, just progress.",
    "Future you is cheering.",
    "Drink water. Touch grass. Log weight.",
    "Discipline beats motivation—log anyway.",
    "Numbers don’t judge; they guide.",
    "One log closer to goals.",
    "Streaks don’t break themselves.",
    "Goals love graphs.",
    "Data > drama.",
    "Tiny habits, giant results.",
    "You’re not behind, you’re on your way.",
    "Do it for your hiking stamina.",
    "The only bad log is the one you skip.",
    "Progress is a plot line—keep adding points.",
    "Momentum is a superpower.",
    "Your goal weight called; it said 'see you soon'.",
    "Strong today, stronger tomorrow.",
    "Goal met—who is she?! 👑",
    "Halfway there—queen behavior 👑",
    "Gaps happen. Come back happens bigger.",
]

def to_date(d):
    """
    Convert input to datetime.date.
    Supports:
      - str "YYYY-MM-DD"
      - datetime.datetime
      - datetime.date
      - dict with 'date' key (from JSON fallback)
    """
    if isinstance(d, dict) and 'date' in d:
        d = d['date']
    if isinstance(d, str):
        return datetime.fromisoformat(d).date()
    elif isinstance(d, datetime):
        return d.date()
    elif isinstance(d, date):
        return d
    else:
        raise TypeError(f"Invalid date type: {type(d)}")

def pick_daily_quote(quotes: List[str], today_iso: str) -> str:
    # deterministic pick for the day
    idx = (sum(ord(c) for c in today_iso) + len(quotes)) % len(quotes)
    return quotes[idx]

# --- BMI ---
def feet_inches_to_m(height_feet: int, height_inches: int) -> float:
    total_inches = height_feet * 12 + height_inches
    meters = total_inches * 0.0254
    return meters

def bmi_for(weight_kg: float, height_m: float) -> float:
    if height_m <= 0:
        return 0.0
    return round(weight_kg / (height_m ** 2), 2)

def bmi_category(bmi: float) -> Tuple[str, str]:
    # (label, color)
    if bmi < 18.5:
        return "Underweight", "blue"
    if bmi < 25:
        return "Normal", "green"
    if bmi < 30:
        return "Overweight", "orange"
    return "Obese", "red"

# --- rolling averages ---
def rolling_avgs(series: List[Tuple[str, float]], window: int) -> List[Tuple[str, float]]:
    """
    series: [(YYYY-MM-DD, weight)] sorted by date asc
    returns list aligned to input order
    """
    out = []
    q = []
    s = 0.0
    for d, w in series:
        q.append(w)
        s += w
        if len(q) > window:
            s -= q.pop(0)
        out.append((d, round(s / len(q), 2)))
    return out

# --- streaks ---
def compute_streaks(dates_asc: List[str]) -> Tuple[int, int]:
    """
    dates_asc sorted ascending
    Returns (current_streak, best_streak) in days
    """
    if not dates_asc:
        return 0, 0
    
    dates_sorted = sorted(set(dates_asc))  # remove duplicates + sort
    dset = {d.isoformat() for d in dates_sorted}
    
    # current streak
    latest = dates_sorted[-1]
    streak_current = 1
    while (latest - timedelta(days=1)).isoformat() in dset:
        latest -= timedelta(days=1)
        streak_current += 1
        
   # best streak
    streak_best = 1
    for d in dates_sorted:
        current = 1
        while (d - timedelta(days=1)).isoformat() in dset:
            d -= timedelta(days=1)
            current += 1
        streak_best = max(streak_best, current)
        
    return streak_current, streak_best

# --- regression projection ---
def linear_regression_eta(points_asc: List[Tuple[str, float]], goal_weight: float) -> Dict[str, Any]:
    """
    points_asc: [(YYYY-MM-DD, weight)] last up to 30 days, asc
    Returns dict with slope, intercept, eta_date or message.
    """
    dates_sorted = sorted([to_date(d) for d in dates_asc])
    if len(points_asc) < 2:
        return {"slope": 0, "intercept": points_asc[-1][1] if points_asc else None, "eta": None, "message": "Need more data"}
    # x as day index starting at 0
    xs = list(range(len(points_asc)))
    ys = [w for _, w in points_asc]
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs) or 1
    slope = num / den
    intercept = y_mean - slope * x_mean
    # Solve for day k where y = goal_weight => k = (goal - b)/m
    if slope == 0:
        return {"slope": slope, "intercept": intercept, "eta": None, "message": "Trend needs a nudge 😉"}
    k = (goal_weight - intercept) / slope
    # ETA only sensible if k is after last point and slope moves toward goal
    last_day = dates_sorted(points_asc[-1][0])
    towards_goal = (goal_weight < ys[-1] and slope < 0) or (goal_weight > ys[-1] and slope > 0)
    if not towards_goal or k < len(xs) - 1:
        return {"slope": slope, "intercept": intercept, "eta": None, "message": "Trend needs a nudge 😉"}
    eta = last_day + timedelta(days=round(k - (len(xs) - 1)))
    return {"slope": round(slope, 4), "intercept": round(intercept, 2), "eta": eta.isoformat(), "message": None}

# --- achievements engine ---
ACHIEVEMENTS = [
    ("first_entry", "First entry", "🏁", "Log your first weight."),
    ("first_week", "First week", "🗓️", "7 logs total."),
    ("streak_3", "On a roll (3)", "🔥", "3-day streak."),
    ("streak_7", "Streak legend (7)", "⚡", "7-day streak."),
    ("streak_14", "Two weeks!", "🏅", "14-day streak."),
    ("streak_30", "Month machine", "💪", "30-day streak."),
    ("early_bird", "Early bird", "🌅", "Logged before 08:00 three times."),
    ("night_owl", "Night owl", "🌙", "Logged after 22:00 three times."),
    ("first_kilo_lost", "First kilo down", "📉", "Lost ≥1 kg since start."),
    ("five_kilos_lost", "High five", "🖐️", "Lost ≥5 kg since start."),
    ("goal_halfway", "Halfway hero", "🚀", "Halfway to goal."),
    ("goal_crusher", "Goal crusher", "👑", "Reached goal!"),
    ("weekend_warrior", "Weekend warrior", "🛡️", "Sat & Sun logs, 3 weekends in a row."),
    ("comeback_kid", "Comeback kid", "🔁", "Return after 7+ day gap."),
    ("consistency_queen", "Consistency queen", "👑", "20 logs in 30 days."),
    ("hydration_hero", "Hydration hero", "💧", "10 consecutive logs (now drink water)."),
    ("graph_gazer", "Graph gazer", "📊", "Opened dashboard 20 times."),
    ("data_ninja", "Data ninja", "🥷", "Edited entries 5+ times."),
    ("share_the_wins", "Share the wins", "📤", "Exported your data."),
    ("clean_sheet", "Clean sheet", "🧼", "Logged every day for a calendar month."),
    ("new_month_new_me", "New month, new me", "🆕", "First log of a month for 3 months."),
    ("bounce_back", "Bounce back", "🧠", "After +2 kg uptick, logged next day."),
    ("plateau_breaker", "Plateau breaker", "🪨", "14 days flat then drop ≥0.5 kg."),
]

def calc_change_from_last(weights_asc: List[Tuple[str,float]]) -> float:
    if len(weights_asc) < 2:
        return 0.0
    return round(weights_asc[-1][1] - weights_asc[-2][1], 2)

def compute_per_row_enrichments(weights_asc: List[Tuple[str,float]], height_m: float) -> List[Dict[str, Any]]:
    """
    Returns each row with: change_from_last, avg7, avg30, bmi, bmi_category
    Input is ASC; output keeps ASC order, the API later sends DESC for tables.
    """
    avg7 = {d: v for d, v in rolling_avgs(weights_asc, 7)}
    avg30 = {d: v for d, v in rolling_avgs(weights_asc, 30)}
    out = []
    for i, (d, w) in enumerate(weights_asc):
        prev_w = weights_asc[i-1][1] if i > 0 else None
        change = round(w - prev_w, 2) if prev_w is not None else 0.0
        bmi_val = bmi_for(w, height_m)
        cat, color = bmi_category(bmi_val)
        out.append({
            "date": d,
            "weight": round(w, 2),
            "change_from_last": change,
            "avg7": avg7[d],
            "avg30": avg30[d],
            "bmi": bmi_val,
            "bmi_category": cat,
            "bmi_color": color
        })
    return out

def weekend_index(dt: date) -> int:
    # Monday=0 ... Sunday=6 ; weekend are 5,6
    return dt.weekday()

def achievements_for(now_iso: str,
                     profile: Dict[str, Any],
                     weights_asc: List[Tuple[str,float]],
                     unlocked: List[str],
                     edit_count: int,
                     dash_opens: int,
                     exported: bool) -> List[str]:
    """
    Returns newly unlocked achievement keys.
    """
    newly = []
    if not weights_asc:
        return newly
    #dset = [datetime.fromisoformat(d).date() for d, _ in weights_asc]
    
    print("weights_asc:", weights_asc, type(weights_asc))
    for i, item in enumerate(weights_asc):
        print(i, item, type(item), [type(x) for x in item])
    
    dset = [to_date(d) for d, _ in weights_asc]
    wvals = [w for _, w in weights_asc]
    total_logs = len(weights_asc)
    # 1) first_entry
    if total_logs >= 1 and "first_entry" not in unlocked:
        newly.append("first_entry")
    # 2) first_week
    if total_logs >= 7 and "first_week" not in unlocked:
        newly.append("first_week")
    # streaks:
    cur, best = compute_streaks([d.isoformat() for d in dset])
    for k, req in [("streak_3", 3), ("streak_7", 7), ("streak_14", 14), ("streak_30", 30)]:
        if best >= req and k not in unlocked:
            newly.append(k)
    # Early bird / night owl
    # Heuristic: entries dated "today" at specific times aren't stored; we emulate using created_at not available here.
    # So we'll approximate using local time marker attached via API (weights blueprint passes hour in meta if available)
    # To keep simple, leave to blueprint to call add_achievement when conditions met.

    # Loss milestones
    start = float(profile["starting_weight"])
    last = float(wvals[-1])
    if last <= start - 1 and "first_kilo_lost" not in unlocked:
        newly.append("first_kilo_lost")
    if last <= start - 5 and "five_kilos_lost" not in unlocked:
        newly.append("five_kilos_lost")
    # Halfway & goal
    goal = float(profile["goal_weight"])
    # Direction could be down or up (default assume weight loss)
    halfway = start - (start - goal) / 2.0
    toward_loss = goal < start
    if toward_loss:
        if last <= halfway and "goal_halfway" not in unlocked:
            newly.append("goal_halfway")
        if last <= goal and "goal_crusher" not in unlocked:
            newly.append("goal_crusher")
    else:
        if last >= halfway and "goal_halfway" not in unlocked:
            newly.append("goal_halfway")
        if last >= goal and "goal_crusher" not in unlocked:
            newly.append("goal_crusher")

    # Consistency queen: 20 logs in 30 days
    if total_logs >= 20:
        last30_start = dset[-1] - timedelta(days=29)
        cnt = sum(1 for d in dset if d >= last30_start)
        if cnt >= 20 and "consistency_queen" not in unlocked:
            newly.append("consistency_queen")

    # Clean sheet: every day in a calendar month
    # Check latest month span
    latest = dset[-1]
    month_first = latest.replace(day=1)
    next_month = (month_first + timedelta(days=32)).replace(day=1)
    days_this_month = (next_month - month_first).days
    if all((month_first + timedelta(days=i)) in dset for i in range(days_this_month)) and "clean_sheet" not in unlocked:
        newly.append("clean_sheet")

    # New month new me: first log of month across 3 distinct months
    months = set((d.year, d.month) for d in dset)
    # Check they have at least a "first day of any 3 months"
    firsts = 0
    for (y, m) in months:
        mdates = [d for d in dset if d.year == y and d.month == m]
        if mdates and mdates[0].day <= 3:  # logged in first 3 days counts
            firsts += 1
    if firsts >= 3 and "new_month_new_me" not in unlocked:
        newly.append("new_month_new_me")

    # Comeback kid: gap ≥7 days then resumed
    gaps = [(b - a).days for a, b in zip(dset, dset[1:])]
    if any(g >= 7 for g in gaps) and "comeback_kid" not in unlocked:
        newly.append("comeback_kid")

    # Bounce back: after +2 kg uptick, logged next day
    for i in range(1, len(wvals)):
        if wvals[i] - wvals[i-1] >= 2.0:
            # did they log next day (i+1) ?
            if i + 1 < len(dset) and (dset[i] + timedelta(days=1)) == dset[i+1]:
                if "bounce_back" not in unlocked:
                    newly.append("bounce_back")
                    break

    # Plateau breaker: 14 days flat (±0.1) then drop ≥0.5
    if len(wvals) >= 16:
        for i in range(14, len(wvals)-1):
            flat = all(abs(wvals[j] - wvals[j-1]) <= 0.1 for j in range(i-13, i+1))
            drop = (wvals[i+1] <= wvals[i] - 0.5)
            if flat and drop and "plateau_breaker" not in unlocked:
                newly.append("plateau_breaker")
                break

    # Graph gazer: dashboard opens
    if dash_opens >= 20 and "graph_gazer" not in unlocked:
        newly.append("graph_gazer")

    # Data ninja: edited count
    if edit_count >= 5 and "data_ninja" not in unlocked:
        newly.append("data_ninja")

    # Share the wins:
    if exported and "share_the_wins" not in unlocked:
        newly.append("share_the_wins")

    # Hydration hero will be triggered by streak ≥10
    if cur >= 10 and "hydration_hero" not in unlocked:
        newly.append("hydration_hero")

    return newly
