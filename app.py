"""
app.py – NutriSmart: Intelligent Nutrition Web Application
Author  : Ali Aizhigitov  (19271590)
Module  : COMP6013 Computing Project 2025-26
Supervisor: David Lightfoot

A Flask-based web application for dietary logging, nutritional analysis,
and intelligent feedback via a rule-based expert system.

Run with:
    python app.py
or for production:
    flask --app app run --host 0.0.0.0
"""

import os
import json
from datetime import date, datetime, timedelta
from functools import wraps
from dotenv import load_dotenv

load_dotenv()  # Load API keys and secrets from .env file

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, g
)
from werkzeug.security import generate_password_hash, check_password_hash

import database as db
from expert_system import analyse
from ai_features import (
    meal_recommender, 
    predict_weekly_trend, 
    detect_eating_anomalies,
    generate_daily_summary
)

# ─────────────────────────────────────────────
#  Application factory
# ─────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nutrismart-dev-secret-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'


# ─────────────────────────────────────────────
#  Database initialisation
# ─────────────────────────────────────────────

with app.app_context():
    db.init_db()
    db.seed_food_database()


# ─────────────────────────────────────────────
#  Authentication helpers
# ─────────────────────────────────────────────

def login_required(f):
    """Decorator to protect routes that require authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def current_user():
    """Return current user dict or None."""
    user_id = session.get('user_id')
    if user_id:
        return db.get_user_by_id(user_id)
    return None


@app.before_request
def load_logged_in_user():
    g.user = current_user()


# ─────────────────────────────────────────────
#  Context processors
# ─────────────────────────────────────────────

@app.context_processor
def inject_globals():
    return {
        'user': g.user,
        'today': date.today().isoformat(),
        'now': datetime.now(),
    }


# ─────────────────────────────────────────────
#  Auth routes
# ─────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username  = request.form.get('username', '').strip().lower()
        email     = request.form.get('email', '').strip().lower()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')
        full_name = request.form.get('full_name', '').strip()

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not email or '@' not in email:
            errors.append('Please enter a valid email address.')
        if len(password) < 8:
            errors.append('Password must be at least 8 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if db.get_user_by_username(username):
            errors.append('That username is already taken.')
        if db.get_user_by_email(email):
            errors.append('An account with that email already exists.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html')

        user_id = db.create_user(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name,
        )
        session['user_id'] = user_id
        flash(f'Welcome to NutriSmart, {full_name or username}! Complete your profile below.', 'success')
        return redirect(url_for('profile'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip().lower()
        password   = request.form.get('password', '')

        user = db.get_user_by_username(identifier) or db.get_user_by_email(identifier)
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            flash(f'Welcome back, {user["full_name"] or user["username"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username/email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────
#  Dashboard
# ─────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    user_id   = session['user_id']
    user      = g.user
    today_str = date.today().isoformat()
    goals     = db.get_goals(user_id)
    totals    = db.get_daily_totals(user_id, today_str)
    meals     = db.get_meals_for_date(user_id, today_str)
    water_ml  = db.get_water_for_date(user_id, today_str)
    weekly    = db.get_weekly_summary(user_id)

    # Group meals by type
    meals_by_type = {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []}
    for m in meals:
        meals_by_type[m['meal_type']].append(m)

    # Expert system analysis
    sugar_streak = db.get_sugar_streak(user_id, goals['sugar_limit'])
    current_hour = datetime.now().hour
    feedbacks, wm = analyse(
        totals=totals,
        goals=goals,
        user=user,
        water_ml=water_ml,
        sugar_streak=sugar_streak,
        meal_count=len(meals),
        hour=current_hour,
    )

    # Save feedback to DB
    db.save_feedback(user_id, feedbacks, today_str)

    # AI-powered insights
    ai_summary = generate_daily_summary(user_id, totals, goals, feedbacks)
    anomalies = detect_eating_anomalies(user_id, {
        'cal': totals.get('calories', 0),
        'prot': totals.get('protein_g', 0),
        'sug': totals.get('sugar_g', 0),
        'meal_count': len(meals)
    })

    # Calculate progress percentages for UI
    def pct(val, target):
        if not target:
            return 0
        return min(round((val / target) * 100), 150)

    progress = {
        'calories': pct(totals.get('calories', 0), goals['calories_target']),
        'protein':  pct(totals.get('protein_g', 0), goals['protein_target']),
        'carbs':    pct(totals.get('carbs_g', 0), goals['carbs_target']),
        'fat':      pct(totals.get('fat_g', 0), goals['fat_target']),
        'fiber':    pct(totals.get('fiber_g', 0), goals['fiber_target']),
        'water':    pct(water_ml, goals['water_target_ml']),
    }

    # Weekly chart data (JSON)
    chart_labels = [w['log_date'][-5:] for w in weekly]  # MM-DD
    chart_calories = [round(w['calories']) for w in weekly]
    chart_protein  = [round(w['protein_g'], 1) for w in weekly]

    return render_template(
        'dashboard.html',
        totals=totals,
        goals=goals,
        meals_by_type=meals_by_type,
        water_ml=water_ml,
        feedbacks=feedbacks,
        progress=progress,
        wm=wm,
        chart_labels=json.dumps(chart_labels),
        chart_calories=json.dumps(chart_calories),
        chart_protein=json.dumps(chart_protein),
        today=today_str,
        ai_summary=ai_summary,
        anomalies=anomalies,
    )


# ─────────────────────────────────────────────
#  AI Recommendations
# ─────────────────────────────────────────────

@app.route('/ai-recommendations')
@login_required
def ai_recommendations():
    user_id   = session['user_id']
    today_str = date.today().isoformat()
    goals     = db.get_goals(user_id)
    totals    = db.get_daily_totals(user_id, today_str)
    
    # Determine current meal type based on time
    hour = datetime.now().hour
    if hour >= 5 and hour < 11:
        meal_type = 'breakfast'
    elif hour >= 11 and hour < 15:
        meal_type = 'lunch'
    elif hour >= 17 and hour < 21:
        meal_type = 'dinner'
    else:
        meal_type = 'snack'
    
    # Get AI recommendations for all meal types
    recommendations = {
        'breakfast': meal_recommender.get_recommendations(user_id, totals, goals, 'breakfast', 5),
        'lunch': meal_recommender.get_recommendations(user_id, totals, goals, 'lunch', 5),
        'dinner': meal_recommender.get_recommendations(user_id, totals, goals, 'dinner', 5),
        'snack': meal_recommender.get_recommendations(user_id, totals, goals, 'snack', 5),
    }
    
    # Get predictive analytics
    predictions = {
        'calories': predict_weekly_trend(user_id, 'calories'),
        'protein': predict_weekly_trend(user_id, 'protein_g'),
        'sugar': predict_weekly_trend(user_id, 'sugar_g'),
    }
    
    return render_template(
        'ai_recommendations.html',
        recommendations=recommendations,
        current_meal_type=meal_type,
        totals=totals,
        goals=goals,
        predictions=predictions,
    )


# ─────────────────────────────────────────────
#  Meal logging
# ─────────────────────────────────────────────

@app.route('/log-meal', methods=['GET', 'POST'])
@login_required
def log_meal():
    if request.method == 'POST':
        user_id   = session['user_id']
        meal_type = request.form.get('meal_type')
        food_name = request.form.get('food_name', '').strip()
        try:
            quantity_g = float(request.form.get('quantity_g', 100))
            calories   = float(request.form.get('calories', 0))
            protein_g  = float(request.form.get('protein_g', 0))
            carbs_g    = float(request.form.get('carbs_g', 0))
            fat_g      = float(request.form.get('fat_g', 0))
            sugar_g    = float(request.form.get('sugar_g', 0))
            fiber_g    = float(request.form.get('fiber_g', 0))
            sodium_mg  = float(request.form.get('sodium_mg', 0))
        except (ValueError, TypeError):
            flash('Invalid nutritional values. Please check your input.', 'danger')
            return redirect(url_for('log_meal'))

        log_date = request.form.get('log_date', date.today().isoformat())
        notes    = request.form.get('notes', '').strip()

        if not food_name:
            flash('Please enter a food name.', 'danger')
            return redirect(url_for('log_meal'))
        if meal_type not in ('breakfast', 'lunch', 'dinner', 'snack'):
            flash('Please select a valid meal type.', 'danger')
            return redirect(url_for('log_meal'))

        db.add_meal(
            user_id=user_id, meal_type=meal_type, food_name=food_name,
            quantity_g=quantity_g, calories=calories, protein_g=protein_g,
            carbs_g=carbs_g, fat_g=fat_g, sugar_g=sugar_g,
            fiber_g=fiber_g, sodium_mg=sodium_mg, log_date=log_date, notes=notes
        )
        flash(f'"{food_name}" logged successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('log_meal.html', today=date.today().isoformat())


@app.route('/delete-meal/<int:meal_id>', methods=['POST'])
@login_required
def delete_meal(meal_id):
    db.delete_meal(meal_id, session['user_id'])
    flash('Meal entry deleted.', 'info')
    return redirect(url_for('dashboard'))


@app.route('/log-water', methods=['POST'])
@login_required
def log_water():
    try:
        amount_ml = int(request.form.get('amount_ml', 0))
        if amount_ml <= 0:
            raise ValueError
    except (ValueError, TypeError):
        flash('Please enter a valid water amount.', 'danger')
        return redirect(url_for('dashboard'))
    db.add_water(session['user_id'], amount_ml)
    flash(f'{amount_ml}ml of water logged!', 'success')
    return redirect(url_for('dashboard'))


# ─────────────────────────────────────────────
#  Food search API (AJAX)
# ─────────────────────────────────────────────

@app.route('/api/foods/search')
@login_required
def api_food_search():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    foods = db.search_foods(query, limit=10)
    return jsonify(foods)


@app.route('/api/foods/<int:food_id>')
@login_required
def api_food_detail(food_id):
    food = db.get_food_by_id(food_id)
    if not food:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(food)


# ─────────────────────────────────────────────
#  History view
# ─────────────────────────────────────────────

@app.route('/history')
@login_required
def history():
    user_id  = session['user_id']
    goals    = db.get_goals(user_id)

    # Show last 30 days
    days = []
    for i in range(30):
        d     = (date.today() - timedelta(days=i)).isoformat()
        tots  = db.get_daily_totals(user_id, d)
        water = db.get_water_for_date(user_id, d)
        meal_count = len(db.get_meals_for_date(user_id, d))
        days.append({
            'date':       d,
            'calories':   round(tots.get('calories', 0)),
            'protein_g':  round(tots.get('protein_g', 0), 1),
            'carbs_g':    round(tots.get('carbs_g', 0), 1),
            'fat_g':      round(tots.get('fat_g', 0), 1),
            'sugar_g':    round(tots.get('sugar_g', 0), 1),
            'fiber_g':    round(tots.get('fiber_g', 0), 1),
            'sodium_mg':  round(tots.get('sodium_mg', 0)),
            'water_ml':   water,
            'meal_count': meal_count,
        })

    return render_template('history.html', days=days, goals=goals)


# ─────────────────────────────────────────────
#  Goals settings
# ─────────────────────────────────────────────

@app.route('/goals', methods=['GET', 'POST'])
@login_required
def goals():
    user_id = session['user_id']
    current_goals = db.get_goals(user_id)

    if request.method == 'POST':
        try:
            kwargs = {
                'calories_target': int(request.form.get('calories_target', 2000)),
                'protein_target':  float(request.form.get('protein_target', 50)),
                'carbs_target':    float(request.form.get('carbs_target', 250)),
                'fat_target':      float(request.form.get('fat_target', 70)),
                'sugar_limit':     float(request.form.get('sugar_limit', 50)),
                'fiber_target':    float(request.form.get('fiber_target', 25)),
                'sodium_limit':    float(request.form.get('sodium_limit', 2300)),
                'water_target_ml': int(request.form.get('water_target_ml', 2000)),
            }
            db.update_goals(user_id, **kwargs)
            flash('Goals updated successfully!', 'success')
        except (ValueError, TypeError):
            flash('Please enter valid numeric values for all goals.', 'danger')
        return redirect(url_for('goals'))

    return render_template('goals.html', goals=current_goals)


# ─────────────────────────────────────────────
#  Profile
# ─────────────────────────────────────────────

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']

    if request.method == 'POST':
        try:
            kwargs = {
                'full_name':     request.form.get('full_name', '').strip(),
                'age':           int(request.form.get('age', 0)) or None,
                'weight_kg':     float(request.form.get('weight_kg', 0)) or None,
                'height_cm':     float(request.form.get('height_cm', 0)) or None,
                'gender':        request.form.get('gender') or None,
                'activity_level': request.form.get('activity_level', 'moderate'),
            }
            db.update_user_profile(user_id, **kwargs)
            g.user = db.get_user_by_id(user_id)
            flash('Profile updated!', 'success')
        except (ValueError, TypeError):
            flash('Please enter valid values.', 'danger')
        return redirect(url_for('profile'))

    return render_template('profile.html', user=g.user)


# ─────────────────────────────────────────────
#  Feedback / Insights page
# ─────────────────────────────────────────────

@app.route('/insights')
@login_required
def insights():
    user_id   = session['user_id']
    user      = g.user
    today_str = date.today().isoformat()
    goals     = db.get_goals(user_id)
    totals    = db.get_daily_totals(user_id, today_str)
    meals     = db.get_meals_for_date(user_id, today_str)
    water_ml  = db.get_water_for_date(user_id, today_str)
    weekly    = db.get_weekly_summary(user_id)

    sugar_streak = db.get_sugar_streak(user_id, goals['sugar_limit'])
    feedbacks, wm = analyse(
        totals=totals, goals=goals, user=user, water_ml=water_ml,
        sugar_streak=sugar_streak, meal_count=len(meals),
        hour=datetime.now().hour,
    )

    # Prepare weekly chart data for all macros
    chart_data = {
        'labels':  [w['log_date'][-5:] for w in weekly],
        'calories': [round(w['calories']) for w in weekly],
        'protein':  [round(w['protein_g'], 1) for w in weekly],
        'carbs':    [round(w['carbs_g'], 1) for w in weekly],
        'fat':      [round(w['fat_g'], 1) for w in weekly],
        'sugar':    [round(w['sugar_g'], 1) for w in weekly],
        'fiber':    [round(w['fiber_g'], 1) for w in weekly],
    }

    # Compute averages
    if weekly:
        avg_calories = round(sum(w['calories'] for w in weekly) / len(weekly))
        avg_protein  = round(sum(w['protein_g'] for w in weekly) / len(weekly), 1)
    else:
        avg_calories = avg_protein = 0

    # AI predictions
    predictions = {
        'calories': predict_weekly_trend(user_id, 'calories'),
        'protein': predict_weekly_trend(user_id, 'protein_g'),
        'sugar': predict_weekly_trend(user_id, 'sugar_g'),
        'fiber': predict_weekly_trend(user_id, 'fiber_g'),
    }

    return render_template(
        'insights.html',
        feedbacks=feedbacks,
        wm=wm,
        goals=goals,
        chart_data=json.dumps(chart_data),
        avg_calories=avg_calories,
        avg_protein=avg_protein,
        sugar_streak=sugar_streak,
        predictions=predictions,
    )


# ─────────────────────────────────────────────
#  AI Features
# ─────────────────────────────────────────────

@app.route('/ai-chat', methods=['GET', 'POST'])
@login_required
def ai_chat():
    """AI Nutritionist Chat - ask questions and get personalized advice."""
    if request.method == 'POST':
        user_message = request.form.get('message', '').strip()
        if not user_message:
            return jsonify({'error': 'Message required'}), 400
        
        # Get user context
        user_id = session['user_id']
        user = g.user
        goals = db.get_goals(user_id)
        today_str = date.today().isoformat()
        totals = db.get_daily_totals(user_id, today_str)
        recent_meals = db.get_meals_for_date(user_id, today_str)
        
        # Build context for AI
        context = f"""You are an expert nutritionist helping {user.get('full_name') or user['username']}.

USER PROFILE:
- Age: {user.get('age') or 'not specified'}
- Weight: {user.get('weight_kg') or 'not specified'} kg
- Height: {user.get('height_cm') or 'not specified'} cm
- Activity: {user.get('activity_level', 'moderate')}

DAILY GOALS:
- Calories: {goals['calories_target']} kcal
- Protein: {goals['protein_target']}g
- Carbs: {goals['carbs_target']}g
- Fat: {goals['fat_target']}g

TODAY'S INTAKE SO FAR:
- Calories: {totals.get('calories', 0):.0f} kcal
- Protein: {totals.get('protein_g', 0):.1f}g
- Carbs: {totals.get('carbs_g', 0):.1f}g
- Fat: {totals.get('fat_g', 0):.1f}g
- Sugar: {totals.get('sugar_g', 0):.1f}g

RECENT MEALS: {len(recent_meals)} logged today

Provide concise, evidence-based nutritional advice. Be encouraging and specific."""

        # Call Claude API
        try:
            import json
            import urllib.request
            
            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": context + "\n\nUser question: " + user_message}
                ]
            }
            
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                    "x-api-key": os.environ.get('ANTHROPIC_API_KEY', '')
                }
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                ai_response = result['content'][0]['text']
                return jsonify({'response': ai_response})
        except Exception as e:
            return jsonify({'response': f"I'm having trouble connecting right now. Here's general advice based on your data: You've consumed {totals.get('calories', 0):.0f} out of {goals['calories_target']} kcal today. Try to maintain a balanced diet with adequate protein, vegetables, and hydration."})
    
    return render_template('ai_chat.html')


@app.route('/ai-parse-meal', methods=['POST'])
@login_required
def ai_parse_meal():
    """Parse natural language meal description using AI."""
    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Text required'}), 400
    
    prompt = f"""Parse this meal description into structured JSON. Extract all foods mentioned.

Input: "{text}"

Return ONLY valid JSON (no markdown, no explanation) in this exact format:
{{
  "foods": [
    {{
      "name": "food name",
      "quantity_g": estimated grams,
      "calories": estimated calories,
      "protein_g": estimated protein,
      "carbs_g": estimated carbs,
      "fat_g": estimated fat,
      "sugar_g": estimated sugar,
      "fiber_g": estimated fiber,
      "sodium_mg": estimated sodium
    }}
  ]
}}

Use reasonable estimates. For example: "sandwich" = 150g, "apple" = 180g, "chicken breast" = 150g."""

    try:
        import json
        import urllib.request
        
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": os.environ.get('ANTHROPIC_API_KEY', '')
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            ai_text = result['content'][0]['text'].strip()
            # Remove markdown code blocks if present
            if ai_text.startswith('```'):
                ai_text = ai_text.split('\n', 1)[1]
                ai_text = ai_text.rsplit('```', 1)[0].strip()
            if ai_text.startswith('json'):
                ai_text = ai_text[4:].strip()
            
            parsed = json.loads(ai_text)
            return jsonify(parsed)
    except Exception as e:
        return jsonify({'error': f'Parse failed: {str(e)}'}), 500


@app.route('/ai-recommend')
@login_required
def ai_recommend():
    """Get AI meal recommendations based on current intake."""
    user_id = session['user_id']
    user = g.user
    goals = db.get_goals(user_id)
    today_str = date.today().isoformat()
    totals = db.get_daily_totals(user_id, today_str)
    
    # Calculate remaining macros
    remaining = {
        'calories': goals['calories_target'] - totals.get('calories', 0),
        'protein': goals['protein_target'] - totals.get('protein_g', 0),
        'carbs': goals['carbs_target'] - totals.get('carbs_g', 0),
        'fat': goals['fat_target'] - totals.get('fat_g', 0),
    }
    
    prompt = f"""As a nutritionist, suggest 3 specific meal ideas for someone who needs:
- {remaining['calories']:.0f} more calories
- {remaining['protein']:.1f}g more protein  
- {remaining['carbs']:.1f}g more carbs
- {remaining['fat']:.1f}g more fat

Provide 3 concise meal suggestions (1-2 sentences each) that would help meet these targets. Be specific about foods and portions."""

    try:
        import json
        import urllib.request
        
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 800,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": os.environ.get('ANTHROPIC_API_KEY', '')
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            recommendations = result['content'][0]['text']
            return jsonify({'recommendations': recommendations, 'remaining': remaining})
    except Exception as e:
        return jsonify({'error': str(e), 'remaining': remaining}), 500


# ─────────────────────────────────────────────
#  Error handlers
# ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message='Page not found.'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code=500, message='Internal server error.'), 500


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
