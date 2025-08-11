import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.urandom(24)

WEIGHT_DATA_FILE = 'data/weight_data.json'
PROFILE_DATA_FILE = 'data/profile_data.json'

def load_data(file_path, default_data):
    if not os.path.exists('data'):
        os.makedirs('data')
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data

def save_data(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def calculate_bmi(weight_kg, height_cm):
    if height_cm > 0:
        height_m = height_cm / 100
        return weight_kg / (height_m ** 2)
    return 0

def get_bmi_category(bmi):
    if bmi == 0:
        return {"category": "Unknown", "color": "gray"}
    elif bmi < 18.5:
        return {"category": "Underweight", "color": "blue"}
    elif 18.5 <= bmi < 25:
        return {"category": "Normal", "color": "green"}
    elif 25 <= bmi < 30:
        return {"category": "Overweight", "color": "orange"}
    else:
        return {"category": "Obese", "color": "red"}

def get_streak(weight_data):
    """Calculate how many days in a row the user has logged weight."""
    if not weight_data:
        return 0

    dates = sorted([datetime.strptime(entry['date'], '%Y-%m-%d').date() for entry in weight_data], reverse=True)
    streak = 1
    for i in range(1, len(dates)):
        if (dates[i-1] - dates[i]).days == 1:
            streak += 1
        else:
            break
    return streak

def get_weight_on_or_before_date(weight_data, target_date):
    for entry in reversed(weight_data):
        entry_date = datetime.strptime(entry['date'], '%Y-%m-%d').date()
        if entry_date <= target_date:
            return entry['weight']
    return None

def add_stats_to_entries(weight_data):
    # Sort ascending by date for this logic
    weight_data_sorted = sorted(weight_data, key=lambda x: x['date'])
    enhanced_entries = []
    prev_weight = None
    weights_last_7 = []
    weights_last_30 = []
    today = datetime.now().date()

    for entry in weight_data_sorted:
        date_obj = datetime.strptime(entry['date'], '%Y-%m-%d').date()
        weight = entry['weight']
        change = None
        avg_7 = None
        avg_30 = None

        if prev_weight is not None:
            change = round(weight - prev_weight, 2)

        # Build lists for averages
        if (today - date_obj).days < 7:
            weights_last_7.append(weight)
        if (today - date_obj).days < 30:
            weights_last_30.append(weight)

        avg_7 = round(sum(weights_last_7) / len(weights_last_7), 2) if weights_last_7 else None
        avg_30 = round(sum(weights_last_30) / len(weights_last_30), 2) if weights_last_30 else None

        enhanced_entries.append({
            "date": entry['date'],
            "weight": weight,
            "change": change,
            "avg_7": avg_7,
            "avg_30": avg_30,
        })

        prev_weight = weight

    # Reverse so latest date first
    return list(reversed(enhanced_entries))

def get_achievements(profile, current_weight, weight_data, bmi):
    achievements = [
        {"icon": "🐦", "name": "Early Bird", "description": "Log your weight before 8 AM three days in a row.", "unlocked": False},  # Add time-based streak logic
        {"icon": "💧", "name": "Hydration Hero", "description": "Track weight for 7 consecutive days.", "unlocked": False},  # Add streak check
        {"icon": "📈", "name": "Steady Climber", "description": "Maintain weight loss for 4 weeks straight.", "unlocked": False},  # No weight gain streak
        {"icon": "🎢", "name": "Weight Fluctuation Master", "description": "Reduced weight fluctuation below 0.5 kg for 2 weeks.", "unlocked": False},  # Variance check
        {"icon": "🔄", "name": "Back on Track", "description": "After a week without logging, log again and keep consistent for 3 days.", "unlocked": False},  # Comeback streak
        {"icon": "🚶‍♂️", "name": "First Step", "description": "Log your very first weight entry.", "unlocked": len(session.get('weight_data', [])) >= 1},
        {"icon": "🎯", "name": "Halfway There", "description": "Reach halfway between starting and goal weight.", "unlocked": current_weight <= (profile.get('starting_weight', 0) + profile.get('goal_weight', 0)) / 2},
        {"icon": "🏆", "name": "Goal Getter", "description": "Hit your goal weight.", "unlocked": current_weight <= profile.get('goal_weight', 0)},
        {"icon": "⚔️", "name": "Weekly Warrior", "description": "Log your weight every day for 7 days straight.", "unlocked": False},  # 7-day streak logic
        {"icon": "📅", "name": "Monthly Master", "description": "Log every day for an entire month.", "unlocked": False},  # 30-day streak logic
        {"icon": "🔨", "name": "Plateau Breaker", "description": "Break a weight plateau lasting more than 2 weeks.", "unlocked": False},  # Weight change after plateau
        {"icon": "💥", "name": "Kilo Crusher", "description": "Lose 5 kg from your starting weight.", "unlocked": current_weight <= profile.get('starting_weight', 0) - 5},
        {"icon": "🔥", "name": "Double Trouble", "description": "Lose 10 kg from your starting weight.", "unlocked": current_weight <= profile.get('starting_weight', 0) - 10},
        {"icon": "👑", "name": "BMI Boss", "description": "Reach a healthy BMI range.", "unlocked": 18.5 <= bmi <= 24.9},
        {"icon": "💡", "name": "Motivation Maven", "description": "Log weight after a break of 5+ days.", "unlocked": False},  # Detect gap in logs
        {"icon": "🌞", "name": "Early Riser", "description": "Log weight before 6 AM once.", "unlocked": False},  # Time-based single check
        {"icon": "🌙", "name": "Night Owl", "description": "Log weight after 10 PM once.", "unlocked": False},  # Time-based single check
        {"icon": "👑", "name": "Consistency King/Queen", "description": "Have no gaps longer than 2 days between logs for 3 months.", "unlocked": False},  # Long streak check
        {"icon": "🔄", "name": "Trendsetter", "description": "Improve your average weight loss trend compared to last month.", "unlocked": False},  # Trend comparison
        {"icon": "🤸‍♂️", "name": "Comeback Kid", "description": "Regain progress after a weight gain.", "unlocked": False},  # Bounce back logic
        {"icon": "🔄", "name": "Change Maker", "description": "Lose or gain 2 kg in one week.", "unlocked": False},  # Big weekly change
        {"icon": "🤝", "name": "Support Squad", "description": "Share your progress (future feature idea!).", "unlocked": False}  # Placeholder for sharing feature
    ]
    return achievements

@app.route('/')
def index():
    profile_data = session.get('profile')
    weight_data = session.get('weight_data')

    if not profile_data:
        profile_data = load_data(PROFILE_DATA_FILE, None)
        session['profile'] = profile_data

    if not profile_data:
        return render_template(
            'index.html',
            profile_exists=False,
            profile=None,
            current_weight=0,
            starting_weight=0,
            goal_weight=0,
            bmi=0,
            bmi_category={"category": "Unknown", "color": "gray"},
            streak=0,
            chart_labels=json.dumps([]),
            chart_data=json.dumps([]),
            achievements=[],
            achievement_message=None,
            milestone_message=None,
            witty_quote="Let's get started on your journey!",
            now=datetime.now(),
            change_7_days=None,
            change_30_days=None,
            weights=[]
        )

    if not weight_data:
        weight_data = load_data(WEIGHT_DATA_FILE, [])
        session['weight_data'] = weight_data

    weight_data = session.get('weight_data') or []
    weight_data.sort(key=lambda x: x['date'], reverse=True)

    total_height_inches = int(profile_data.get('height_feet', 0)) * 12 + int(profile_data.get('height_inches', 0))
    height_cm = total_height_inches * 2.54

    current_weight = weight_data[0]['weight'] if weight_data else profile_data['starting_weight']
    starting_weight = profile_data.get('starting_weight')
    goal_weight = profile_data.get('goal_weight')

    bmi = calculate_bmi(current_weight, height_cm)
    bmi_category = get_bmi_category(bmi)

    change_7_days = None
    change_30_days = None
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)

    if len(weight_data) >= 2:
        weight_7_days_ago = get_weight_on_or_before_date(weight_data, seven_days_ago)
        weight_30_days_ago = get_weight_on_or_before_date(weight_data, thirty_days_ago)

        if weight_7_days_ago is not None:
            change_7_days = current_weight - weight_7_days_ago

        if weight_30_days_ago is not None:
            change_30_days = current_weight - weight_30_days_ago

    weight_data_with_stats = add_stats_to_entries(weight_data)

    streak = get_streak(weight_data)
    bmi = calculate_bmi(current_weight, height_cm)
    achievements = get_achievements(profile_data, current_weight, weight_data, bmi)

    achievement_message = None
    milestone_message = None

    chart_labels = [entry['date'] for entry in weight_data]
    chart_data = [entry['weight'] for entry in weight_data]

    witty_quotes = [
        "Sweat is just fat crying.",
        "Progress, not perfection.",
        "Strive for progress, not excuses.",
        "Your future self will thank you.",
        "Discipline is choosing between what you want now and what you want most.",
        "One pound at a time, one day at a time.",
        "Tough times don’t last, tough people do.",
        "The only bad workout is the one that didn’t happen.",
        "Believe you can and you're halfway there.",
        "Don’t limit your challenges. Challenge your limits.",
        "Pain is temporary, pride is forever.",
        "Strong is the new skinny.",
        "Fitness is like a relationship. You can’t cheat and expect it to work.",
        "Push yourself because no one else is going to do it for you.",
        "Success starts with self-discipline.",
        "Wake up with determination. Go to bed with satisfaction.",
        "Sore today, strong tomorrow.",
        "If it doesn’t challenge you, it won’t change you.",
        "Your body can stand almost anything. It’s your mind you have to convince.",
        "Good things come to those who sweat."
    ]

    return render_template(
        'index.html',
        profile_exists=True,
        profile=profile_data,
        current_weight=current_weight,
        starting_weight=starting_weight,
        goal_weight=goal_weight,
        bmi=round(bmi, 2),
        bmi_category=bmi_category,
        streak=streak,
        chart_labels=json.dumps(chart_labels),
        chart_data=json.dumps(chart_data),
        achievements=achievements,
        change_7_days=change_7_days,
        change_30_days=change_30_days,
        achievement_message=achievement_message,
        milestone_message=milestone_message,
        witty_quote=witty_quotes[len(weight_data) % len(witty_quotes)] if weight_data else witty_quotes[0],
        now=datetime.now(),
        weights=weight_data_with_stats
    )

@app.route('/set_profile', methods=['POST'])
def set_profile():
    name = request.form['name']
    height_feet = int(request.form['height_feet'])
    height_inches = int(request.form['height_inches'])
    starting_weight = float(request.form['starting_weight'])
    goal_weight = float(request.form['goal_weight'])

    profile = {
        "name": name,
        "height_feet": height_feet,
        "height_inches": height_inches,
        "starting_weight": starting_weight,
        "goal_weight": goal_weight
    }

    session['profile'] = profile
    save_data(PROFILE_DATA_FILE, profile)

    initial_entry = {
        "date": datetime.now().strftime('%Y-%m-%d'),
        "weight": starting_weight
    }
    session['weight_data'] = [initial_entry]
    save_data(WEIGHT_DATA_FILE, [initial_entry])

    return redirect(url_for('index'))

@app.route('/add_weight', methods=['POST'])
def add_weight():
    weight_data = session.get('weight_data', [])
    date = request.form['date']
    weight = float(request.form['weight'])

    new_entry = {"date": date, "weight": weight}

    entry_found = False
    for i, entry in enumerate(weight_data):
        if entry['date'] == date:
            weight_data[i] = new_entry
            entry_found = True
            break

    if not entry_found:
        weight_data.append(new_entry)

    weight_data.sort(key=lambda x: x['date'], reverse=True)

    session['weight_data'] = weight_data
    save_data(WEIGHT_DATA_FILE, weight_data)

    return redirect(url_for('index'))

@app.route('/profile-settings', methods=['GET', 'POST'])
def profile_settings():
    profile_data = session.get('profile')

    if request.method == 'POST':
        profile_data['name'] = request.form['name']
        profile_data['height_feet'] = int(request.form['height_feet'])
        profile_data['height_inches'] = int(request.form['height_inches'])
        profile_data['starting_weight'] = float(request.form['starting_weight'])
        profile_data['goal_weight'] = float(request.form['goal_weight'])

        session['profile'] = profile_data
        save_data(PROFILE_DATA_FILE, profile_data)

        return redirect(url_for('index'))

    return render_template('profile_settings.html', profile=profile_data)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)

