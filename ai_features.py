"""
ai_features.py - Advanced AI/ML features for NutriSmart

Implements:
1. Meal recommendation engine (content-based filtering)
2. Predictive analytics (trend forecasting)
3. Anomaly detection (eating pattern analysis)
4. Smart insights generation (NLP-style)
"""

import math
from datetime import datetime, timedelta
from collections import defaultdict
import database as db


# ══════════════════════════════════════════════════════════════
#  1. AI MEAL RECOMMENDATION ENGINE
# ══════════════════════════════════════════════════════════════

class MealRecommender:
    """
    Content-based recommendation system that suggests meals based on:
    - Current nutritional deficit (what user needs to meet goals)
    - Time of day (breakfast/lunch/dinner appropriate)
    - User's eating history (avoid recent duplicates)
    - Nutritional balance
    """
    
    def __init__(self):
        self.foods_cache = None
    
    def get_recommendations(self, user_id, current_totals, goals, meal_type, top_n=5):
        """
        Generate AI-powered meal recommendations.
        
        Returns list of recommended foods with scores and reasoning.
        """
        # Load all foods
        if not self.foods_cache:
            conn = db.get_db()
            rows = conn.execute("SELECT * FROM foods").fetchall()
            self.foods_cache = [dict(r) for r in rows]
            conn.close()
        
        # Calculate nutritional needs
        cal_need = max(0, goals['calories_target'] - current_totals.get('calories', 0))
        protein_need = max(0, goals['protein_target'] - current_totals.get('protein_g', 0))
        fiber_need = max(0, goals['fiber_target'] - current_totals.get('fiber_g', 0))
        
        # Get recent meals to avoid repetition
        recent_foods = self._get_recent_foods(user_id, days=3)
        
        # Score each food
        recommendations = []
        for food in self.foods_cache:
            score, reason = self._score_food(
                food, cal_need, protein_need, fiber_need, 
                meal_type, recent_foods, goals
            )
            if score > 0:
                recommendations.append({
                    'food': food,
                    'score': score,
                    'reason': reason
                })
        
        # Sort by score and return top N
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        return recommendations[:top_n]
    
    def _score_food(self, food, cal_need, protein_need, fiber_need, 
                    meal_type, recent_foods, goals):
        """Score a food based on multiple factors."""
        score = 0
        reasons = []
        
        # Base nutritional alignment (0-40 points)
        cal_match = min(food['calories_per_100g'] / (cal_need / 3 + 1), 1) * 15
        protein_match = min(food['protein_per_100g'] / (protein_need / 3 + 1), 1) * 15
        fiber_match = min(food['fiber_per_100g'] / (fiber_need / 3 + 1), 1) * 10
        score += cal_match + protein_match + fiber_match
        
        # High protein bonus
        if food['protein_per_100g'] > 20:
            score += 10
            reasons.append("high protein")
        
        # High fiber bonus
        if food['fiber_per_100g'] > 5:
            score += 8
            reasons.append("high fiber")
        
        # Low sugar bonus
        if food['sugar_per_100g'] < 5:
            score += 5
            reasons.append("low sugar")
        
        # Low sodium bonus
        if food['sodium_per_100g'] < 200:
            score += 5
        
        # Meal type appropriateness (0-20 points)
        category = food['category'] or ''
        if meal_type == 'breakfast':
            if any(x in category.lower() for x in ['grain', 'cereal', 'dairy', 'egg', 'fruit']):
                score += 20
                reasons.append("breakfast-appropriate")
        elif meal_type == 'lunch' or meal_type == 'dinner':
            if any(x in category.lower() for x in ['meat', 'fish', 'poultry', 'vegetable', 'legume']):
                score += 20
                reasons.append("meal-appropriate")
        elif meal_type == 'snack':
            if any(x in category.lower() for x in ['fruit', 'nut', 'seed']) or food['calories_per_100g'] < 200:
                score += 20
                reasons.append("snack-appropriate")
        
        # Penalty for recent consumption (-30 points)
        if food['name'] in recent_foods:
            score -= 30
            reasons.append("⚠ eaten recently")
        
        # Penalty for very high calorie
        if food['calories_per_100g'] > 600:
            score -= 10
        
        # Penalty for excessive sugar
        if food['sugar_per_100g'] > goals.get('sugar_limit', 50) * 0.5:
            score -= 15
            reasons.append("⚠ high sugar")
        
        reason_text = ", ".join(reasons) if reasons else "balanced nutrition"
        return max(score, 0), reason_text
    
    def _get_recent_foods(self, user_id, days=3):
        """Get foods eaten in the last N days."""
        conn = db.get_db()
        cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
        rows = conn.execute(
            "SELECT DISTINCT food_name FROM meal_logs WHERE user_id = ? AND log_date >= ?",
            (user_id, cutoff)
        ).fetchall()
        conn.close()
        return {r['food_name'] for r in rows}


# ══════════════════════════════════════════════════════════════
#  2. PREDICTIVE ANALYTICS
# ══════════════════════════════════════════════════════════════

def predict_weekly_trend(user_id, metric='calories'):
    """
    Simple linear regression to predict next 7 days based on last 30 days.
    Returns: {
        'current_avg': float,
        'predicted_7day_avg': float,
        'trend': 'increasing' | 'decreasing' | 'stable',
        'change_percent': float
    }
    """
    # Get last 30 days of data
    conn = db.get_db()
    cutoff = (datetime.now() - timedelta(days=30)).date().isoformat()
    
    query_map = {
        'calories': 'SUM(calories)',
        'protein_g': 'SUM(protein_g)',
        'sugar_g': 'SUM(sugar_g)',
        'fiber_g': 'SUM(fiber_g)',
    }
    
    aggregator = query_map.get(metric, 'SUM(calories)')
    rows = conn.execute(f"""
        SELECT log_date, {aggregator} as value
        FROM meal_logs
        WHERE user_id = ? AND log_date >= ?
        GROUP BY log_date
        ORDER BY log_date
    """, (user_id, cutoff)).fetchall()
    conn.close()
    
    if len(rows) < 7:
        return None
    
    # Simple linear regression: y = mx + b
    n = len(rows)
    sum_x = sum(range(n))
    sum_y = sum(r['value'] for r in rows)
    sum_xy = sum(i * r['value'] for i, r in enumerate(rows))
    sum_x2 = sum(i**2 for i in range(n))
    
    m = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x**2) if (n * sum_x2 - sum_x**2) != 0 else 0
    b = (sum_y - m * sum_x) / n
    
    # Predict average for next 7 days
    predictions = [m * (n + i) + b for i in range(7)]
    predicted_avg = sum(predictions) / 7
    current_avg = sum_y / n
    
    change_pct = ((predicted_avg - current_avg) / current_avg * 100) if current_avg > 0 else 0
    
    if abs(change_pct) < 3:
        trend = 'stable'
    elif change_pct > 0:
        trend = 'increasing'
    else:
        trend = 'decreasing'
    
    return {
        'current_avg': round(current_avg, 1),
        'predicted_7day_avg': round(predicted_avg, 1),
        'trend': trend,
        'change_percent': round(change_pct, 1),
        'metric': metric
    }


# ══════════════════════════════════════════════════════════════
#  3. ANOMALY DETECTION
# ══════════════════════════════════════════════════════════════

def detect_eating_anomalies(user_id, today_totals):
    """
    Detect unusual eating patterns using Z-score method.
    Returns list of anomalies detected.
    """
    # Get last 30 days (excluding today)
    conn = db.get_db()
    cutoff = (datetime.now() - timedelta(days=30)).date().isoformat()
    today_str = datetime.now().date().isoformat()
    
    rows = conn.execute("""
        SELECT 
            SUM(calories) as cal,
            SUM(protein_g) as prot,
            SUM(sugar_g) as sug,
            COUNT(*) as meal_count
        FROM meal_logs
        WHERE user_id = ? AND log_date >= ? AND log_date < ?
        GROUP BY log_date
    """, (user_id, cutoff, today_str)).fetchall()
    conn.close()
    
    if len(rows) < 7:
        return []
    
    anomalies = []
    
    # Calculate stats for each metric
    for metric, label, threshold in [
        ('cal', 'calories', 2.0),
        ('prot', 'protein', 2.0),
        ('sug', 'sugar', 1.8),
        ('meal_count', 'meal frequency', 2.0)
    ]:
        values = [r[metric] for r in rows if r[metric]]
        if not values:
            continue
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = math.sqrt(variance)
        
        today_val = today_totals.get(metric, 0)
        
        if std_dev > 0:
            z_score = abs((today_val - mean) / std_dev)
            if z_score > threshold:
                direction = "significantly higher" if today_val > mean else "significantly lower"
                anomalies.append({
                    'metric': label,
                    'z_score': round(z_score, 2),
                    'today_value': round(today_val, 1),
                    'avg_value': round(mean, 1),
                    'message': f"Your {label} today ({round(today_val, 1)}) is {direction} than your 30-day average ({round(mean, 1)})"
                })
    
    return anomalies


# ══════════════════════════════════════════════════════════════
#  4. SMART NATURAL LANGUAGE INSIGHTS
# ══════════════════════════════════════════════════════════════

def generate_daily_summary(user_id, totals, goals, feedbacks):
    """
    Generate a conversational, personalized daily summary using NLG techniques.
    """
    insights = []
    
    # Overall assessment
    cal_pct = (totals.get('calories', 0) / goals['calories_target'] * 100) if goals['calories_target'] > 0 else 0
    
    if cal_pct < 50:
        tone = "concerning"
        emoji = "😟"
    elif cal_pct < 80:
        tone = "improving"
        emoji = "📈"
    elif cal_pct <= 110:
        tone = "excellent"
        emoji = "🎯"
    else:
        tone = "high"
        emoji = "⚠️"
    
    # Count feedback severity
    dangers = sum(1 for f in feedbacks if f['severity'] == 'danger')
    warnings = sum(1 for f in feedbacks if f['severity'] == 'warning')
    
    if dangers > 0:
        summary = f"{emoji} Today's nutrition shows {dangers} critical area(s) requiring immediate attention."
    elif warnings > 2:
        summary = f"{emoji} Your diet today has some imbalances across {warnings} areas."
    elif warnings > 0:
        summary = f"{emoji} Pretty good day overall, with just {warnings} minor area(s) to watch."
    else:
        summary = f"{emoji} Excellent work! Your nutrition is well-balanced today."
    
    insights.append(summary)
    
    # Macro balance insight
    total_cals = totals.get('calories', 1)
    if total_cals > 100:
        p_pct = (totals.get('protein_g', 0) * 4 / total_cals) * 100
        c_pct = (totals.get('carbs_g', 0) * 4 / total_cals) * 100
        f_pct = (totals.get('fat_g', 0) * 9 / total_cals) * 100
        
        macro_msg = f"Your macro split is {round(p_pct)}% protein, {round(c_pct)}% carbs, {round(f_pct)}% fat"
        
        if p_pct > 35:
            macro_msg += " (very high protein - great for muscle building!)"
        elif p_pct < 15:
            macro_msg += " (protein is quite low - consider adding lean protein sources)"
        elif f_pct > 40:
            macro_msg += " (high fat - watch your heart health)"
        else:
            macro_msg += " (well-balanced macros!)"
        
        insights.append(macro_msg)
    
    # Trend insight from predictions
    trend = predict_weekly_trend(user_id, 'calories')
    if trend:
        if trend['trend'] == 'increasing' and trend['change_percent'] > 10:
            insights.append(f"📊 Your calorie intake is trending upward (+{trend['change_percent']}% predicted next week). Consider portion control if weight gain isn't your goal.")
        elif trend['trend'] == 'decreasing' and trend['change_percent'] < -10:
            insights.append(f"📊 Your calorie intake is trending downward ({trend['change_percent']}% predicted next week). Ensure you're eating enough to maintain energy levels.")
        elif trend['trend'] == 'stable':
            insights.append(f"📊 Your calorie intake is stable - great consistency!")
    
    return insights


# Module-level instances
meal_recommender = MealRecommender()
