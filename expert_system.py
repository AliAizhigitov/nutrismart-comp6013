"""
expert_system.py – Rule-Based Expert System for NutriSmart.

Architecture
------------
This module implements a simple forward-chaining expert system.

Working Memory (WM)  : the fact base derived from a user's daily nutritional
                       intake, goals, and historical trends.
Rule Base            : a prioritised list of IF-THEN production rules.
Inference Engine     : iterates over rules; any whose conditions match the WM
                       are "fired" and produce a Feedback object.

Rules are written as plain Python dicts so they can be inspected, serialised,
and extended without changing the engine.  Each rule has:

    id         – unique identifier (string)
    priority   – int, lower = higher priority
    severity   – 'info' | 'warning' | 'danger'
    condition  – callable(wm) → bool
    message    – callable(wm) → str  (can embed WM values)
    category   – descriptive tag for the UI

References:
    Jackson, P. (1999) Introduction to Expert Systems. 3rd ed. Addison-Wesley.
    NHS Eatwell Guide (2023) – recommended nutrient intakes.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Callable
import math


# ────────────────────────────────────────────
#  Data structures
# ────────────────────────────────────────────

@dataclass
class Feedback:
    rule_id:  str
    severity: str          # 'info' | 'warning' | 'danger'
    message:  str
    category: str
    icon:     str = "💡"

    def to_dict(self):
        return {
            'rule_id':  self.rule_id,
            'severity': self.severity,
            'message':  self.message,
            'category': self.category,
            'icon':     self.icon,
        }


# ────────────────────────────────────────────
#  Helper / BMR utilities
# ────────────────────────────────────────────

ACTIVITY_MULTIPLIERS = {
    'sedentary':   1.2,
    'light':       1.375,
    'moderate':    1.55,
    'active':      1.725,
    'very_active': 1.9,
}

def compute_bmr(weight_kg, height_cm, age, gender):
    """Mifflin–St Jeor equation."""
    if None in (weight_kg, height_cm, age, gender):
        return None
    if gender == 'male':
        return (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        return (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161


def compute_tdee(bmr, activity_level):
    if bmr is None:
        return None
    mult = ACTIVITY_MULTIPLIERS.get(activity_level, 1.55)
    return bmr * mult


def percentage(actual, target):
    if not target:
        return 0
    return (actual / target) * 100


# ────────────────────────────────────────────
#  Rule base  (IF-THEN production rules)
# ────────────────────────────────────────────

RULES = [
    # ── Calorie rules ──────────────────────────────────────────────────────
    {
        'id': 'CAL_SEVERE_DEFICIT',
        'priority': 1,
        'severity': 'danger',
        'category': 'Calories',
        'icon': '🚨',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['calories_target'] > 0 and
            percentage(wm['calories'], wm['calories_target']) < 50 and
            wm['day_complete']
        ),
        'message': lambda wm: (
            f"You've consumed only {wm['calories']:.0f} kcal today – less than half your "
            f"daily target of {wm['calories_target']} kcal. Severe caloric restriction can "
            f"lead to muscle loss and nutrient deficiencies. Please ensure you eat enough to "
            f"meet your energy needs."
        ),
    },
    {
        'id': 'CAL_DEFICIT',
        'priority': 2,
        'severity': 'warning',
        'category': 'Calories',
        'icon': '⚠️',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['calories_target'] > 0 and
            50 <= percentage(wm['calories'], wm['calories_target']) < 80 and
            wm['day_complete']
        ),
        'message': lambda wm: (
            f"You've logged {wm['calories']:.0f} kcal against a target of "
            f"{wm['calories_target']} kcal ({percentage(wm['calories'], wm['calories_target']):.0f}%). "
            f"Consider adding an additional meal or nutritious snack to meet your energy needs."
        ),
    },
    {
        'id': 'CAL_SURPLUS',
        'priority': 3,
        'severity': 'warning',
        'category': 'Calories',
        'icon': '⚠️',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['calories_target'] > 0 and
            percentage(wm['calories'], wm['calories_target']) > 120
        ),
        'message': lambda wm: (
            f"Today's intake of {wm['calories']:.0f} kcal exceeds your target by "
            f"{wm['calories'] - wm['calories_target']:.0f} kcal "
            f"({percentage(wm['calories'], wm['calories_target']):.0f}% of target). "
            f"Consistent caloric surplus can lead to unintended weight gain. "
            f"Focus on nutrient-dense, lower-calorie options for your next meal."
        ),
    },
    {
        'id': 'CAL_ON_TRACK',
        'priority': 10,
        'severity': 'info',
        'category': 'Calories',
        'icon': '✅',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['calories_target'] > 0 and
            80 <= percentage(wm['calories'], wm['calories_target']) <= 110
        ),
        'message': lambda wm: (
            f"Great work! Your calorie intake of {wm['calories']:.0f} kcal is well within "
            f"your daily target of {wm['calories_target']} kcal. Keep it up!"
        ),
    },

    # ── Protein rules ─────────────────────────────────────────────────────
    {
        'id': 'PROTEIN_LOW',
        'priority': 4,
        'severity': 'warning',
        'category': 'Protein',
        'icon': '💪',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['protein_target'] > 0 and
            percentage(wm['protein_g'], wm['protein_target']) < 70 and
            wm['day_complete']
        ),
        'message': lambda wm: (
            f"Protein intake is low: {wm['protein_g']:.1f}g vs your target of "
            f"{wm['protein_target']}g. Adequate protein supports muscle repair and satiety. "
            f"Consider adding chicken, fish, eggs, legumes, or Greek yogurt to your next meal."
        ),
    },
    {
        'id': 'PROTEIN_HIGH',
        'priority': 8,
        'severity': 'info',
        'category': 'Protein',
        'icon': '💪',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['protein_target'] > 0 and
            percentage(wm['protein_g'], wm['protein_target']) > 150
        ),
        'message': lambda wm: (
            f"You've consumed {wm['protein_g']:.1f}g of protein today – well above your "
            f"{wm['protein_target']}g target. While protein is important, ensure you also "
            f"maintain balanced carbohydrate and fat intake for optimal energy."
        ),
    },

    # ── Sugar rules ────────────────────────────────────────────────────────
    {
        'id': 'SUGAR_DAILY_EXCESS',
        'priority': 2,
        'severity': 'warning',
        'category': 'Sugar',
        'icon': '🍬',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['sugar_limit'] > 0 and
            wm['sugar_g'] > wm['sugar_limit']
        ),
        'message': lambda wm: (
            f"Free sugar intake today is {wm['sugar_g']:.1f}g – exceeding the recommended "
            f"limit of {wm['sugar_limit']}g (NHS guideline: 30g for adults). "
            f"Excess sugar is linked to dental decay and metabolic issues. "
            f"Try replacing sugary snacks with fruit or unsweetened alternatives."
        ),
    },
    {
        'id': 'SUGAR_3DAY_STREAK',
        'priority': 1,
        'severity': 'danger',
        'category': 'Sugar',
        'icon': '🚨',
        'condition': lambda wm: wm.get('sugar_streak', 0) >= 3,
        'message': lambda wm: (
            f"High sugar alert! You have exceeded your sugar limit for "
            f"{wm['sugar_streak']} consecutive days. Persistently high sugar intake "
            f"raises risk of insulin resistance and type 2 diabetes. Consider auditing "
            f"your diet for hidden sugars (sauces, juices, processed foods)."
        ),
    },

    # ── Sodium rules ───────────────────────────────────────────────────────
    {
        'id': 'SODIUM_HIGH',
        'priority': 3,
        'severity': 'warning',
        'category': 'Sodium',
        'icon': '🧂',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['sodium_limit'] > 0 and
            wm['sodium_mg'] > wm['sodium_limit']
        ),
        'message': lambda wm: (
            f"Sodium intake is {wm['sodium_mg']:.0f}mg today – above your "
            f"{wm['sodium_limit']}mg limit (NHS: max 2,300mg). "
            f"High sodium is associated with elevated blood pressure. "
            f"Reduce processed meats, canned foods, and added salt."
        ),
    },

    # ── Fibre rules ────────────────────────────────────────────────────────
    {
        'id': 'FIBRE_LOW',
        'priority': 5,
        'severity': 'warning',
        'category': 'Fibre',
        'icon': '🥦',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['fiber_target'] > 0 and
            percentage(wm['fiber_g'], wm['fiber_target']) < 60 and
            wm['day_complete']
        ),
        'message': lambda wm: (
            f"Dietary fibre is {wm['fiber_g']:.1f}g vs a target of {wm['fiber_target']}g. "
            f"Adequate fibre (NHS: 30g/day) supports gut health and reduces cardiovascular "
            f"risk. Include more whole grains, legumes, vegetables, and fruit."
        ),
    },
    {
        'id': 'FIBRE_GOOD',
        'priority': 9,
        'severity': 'info',
        'category': 'Fibre',
        'icon': '✅',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['fiber_target'] > 0 and
            percentage(wm['fiber_g'], wm['fiber_target']) >= 90
        ),
        'message': lambda wm: (
            f"Excellent fibre intake! {wm['fiber_g']:.1f}g meets your daily target of "
            f"{wm['fiber_target']}g. Your gut microbiome will thank you."
        ),
    },

    # ── Hydration rules ────────────────────────────────────────────────────
    {
        'id': 'WATER_LOW',
        'priority': 4,
        'severity': 'warning',
        'category': 'Hydration',
        'icon': '💧',
        'condition': lambda wm: (
            wm['water_target_ml'] > 0 and
            wm['water_ml'] < (wm['water_target_ml'] * 0.60) and
            wm['day_complete']
        ),
        'message': lambda wm: (
            f"Hydration alert! You've logged only {wm['water_ml']}ml vs a target of "
            f"{wm['water_target_ml']}ml. Adequate water intake supports metabolism, "
            f"concentration, and kidney health. Try setting hourly reminders to drink water."
        ),
    },
    {
        'id': 'WATER_GOOD',
        'priority': 9,
        'severity': 'info',
        'category': 'Hydration',
        'icon': '💧',
        'condition': lambda wm: (
            wm['water_target_ml'] > 0 and
            wm['water_ml'] >= wm['water_target_ml']
        ),
        'message': lambda wm: (
            f"Hydration goal reached! {wm['water_ml']}ml logged today. "
            f"Staying well-hydrated supports energy levels and cognitive function."
        ),
    },

    # ── Macro balance rules ────────────────────────────────────────────────
    {
        'id': 'MACRO_IMBALANCED_FAT',
        'priority': 6,
        'severity': 'warning',
        'category': 'Macronutrients',
        'icon': '⚖️',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['calories'] > 200 and
            (wm['fat_g'] * 9 / wm['calories']) > 0.40
        ),
        'message': lambda wm: (
            f"Fat accounts for {(wm['fat_g'] * 9 / wm['calories'] * 100):.0f}% of today's "
            f"calories (recommended: 20–35%). High fat intake can increase cardiovascular "
            f"risk. Review fatty foods in your log and consider leaner protein sources."
        ),
    },
    {
        'id': 'MACRO_LOW_CARB',
        'priority': 7,
        'severity': 'info',
        'category': 'Macronutrients',
        'icon': '⚖️',
        'condition': lambda wm: (
            wm['meals_logged'] > 0 and
            wm['calories'] > 200 and
            (wm['carbs_g'] * 4 / wm['calories']) < 0.25
        ),
        'message': lambda wm: (
            f"Carbohydrate intake is low ({(wm['carbs_g'] * 4 / wm['calories'] * 100):.0f}% "
            f"of calories; recommended: 45–65%). Carbohydrates are the body's primary energy "
            f"source. Unless you are intentionally following a low-carb diet, consider adding "
            f"whole grains, fruit, or legumes."
        ),
    },

    # ── No meals logged ────────────────────────────────────────────────────
    {
        'id': 'NO_MEALS',
        'priority': 0,
        'severity': 'info',
        'category': 'General',
        'icon': '📋',
        'condition': lambda wm: wm['meals_logged'] == 0,
        'message': lambda wm: (
            "No meals logged yet today. Start by adding your breakfast or first meal to "
            "receive personalised dietary feedback."
        ),
    },

    # ── TDEE mismatch ──────────────────────────────────────────────────────
    {
        'id': 'TARGET_BELOW_TDEE',
        'priority': 8,
        'severity': 'info',
        'category': 'Goals',
        'icon': '🎯',
        'condition': lambda wm: (
            wm.get('tdee') is not None and
            wm['calories_target'] > 0 and
            wm['calories_target'] < wm['tdee'] * 0.85
        ),
        'message': lambda wm: (
            f"Your calorie target ({wm['calories_target']} kcal) is more than 15% below your "
            f"estimated TDEE ({wm['tdee']:.0f} kcal). A large deficit may be unsustainable. "
            f"Consider a moderate deficit of 300–500 kcal/day for healthy weight management."
        ),
    },
]


# ────────────────────────────────────────────
#  Inference Engine
# ────────────────────────────────────────────

class NutritionExpertSystem:
    """
    Forward-chaining inference engine.

    Given a Working Memory dict, evaluate all rules in priority order and
    return a list of Feedback objects for any rules whose conditions are met.
    Only one rule per category fires (highest priority wins) to avoid
    contradictory advice.
    """

    def __init__(self):
        self._rules = sorted(RULES, key=lambda r: r['priority'])

    def build_working_memory(self, totals: dict, goals: dict, user: dict,
                              water_ml: int, sugar_streak: int,
                              meal_count: int, hour: int = 20) -> Dict[str, Any]:
        """
        Construct the working memory (fact base) from raw data.

        Parameters
        ----------
        totals      : daily nutrient totals from the database
        goals       : user's nutrition goals
        user        : user profile (weight, height, age, gender, activity_level)
        water_ml    : total water logged today (ml)
        sugar_streak: consecutive days sugar exceeded limit
        meal_count  : number of meal entries today
        hour        : current hour (0-23) – used to determine if day is 'complete'
        """
        bmr = compute_bmr(
            user.get('weight_kg'),
            user.get('height_cm'),
            user.get('age'),
            user.get('gender'),
        )
        tdee = compute_tdee(bmr, user.get('activity_level', 'moderate'))

        wm = {
            # Actuals
            'calories':    round(totals.get('calories', 0), 1),
            'protein_g':   round(totals.get('protein_g', 0), 1),
            'carbs_g':     round(totals.get('carbs_g', 0), 1),
            'fat_g':       round(totals.get('fat_g', 0), 1),
            'sugar_g':     round(totals.get('sugar_g', 0), 1),
            'fiber_g':     round(totals.get('fiber_g', 0), 1),
            'sodium_mg':   round(totals.get('sodium_mg', 0), 1),
            'water_ml':    water_ml,

            # Targets / limits
            'calories_target': goals.get('calories_target', 2000),
            'protein_target':  goals.get('protein_target', 50),
            'carbs_target':    goals.get('carbs_target', 250),
            'fat_target':      goals.get('fat_target', 70),
            'sugar_limit':     goals.get('sugar_limit', 50),
            'fiber_target':    goals.get('fiber_target', 25),
            'sodium_limit':    goals.get('sodium_limit', 2300),
            'water_target_ml': goals.get('water_target_ml', 2000),

            # Derived / context
            'meals_logged': meal_count,
            'sugar_streak': sugar_streak,
            'day_complete': hour >= 19,   # assume day complete after 7pm
            'bmr':          bmr,
            'tdee':         tdee,
        }
        return wm

    def evaluate(self, wm: Dict[str, Any]) -> List[Feedback]:
        """
        Run forward chaining: return a list of Feedback for all fired rules.
        At most one rule fires per category.
        """
        fired_categories = set()
        results = []
        for rule in self._rules:
            category = rule['category']
            # Allow multiple 'info' rules but only one warning/danger per category
            if rule['severity'] in ('warning', 'danger') and category in fired_categories:
                continue
            try:
                if rule['condition'](wm):
                    msg = rule['message'](wm)
                    results.append(Feedback(
                        rule_id=rule['id'],
                        severity=rule['severity'],
                        message=msg,
                        category=category,
                        icon=rule.get('icon', '💡'),
                    ))
                    if rule['severity'] in ('warning', 'danger'):
                        fired_categories.add(category)
            except (ZeroDivisionError, TypeError, KeyError):
                pass  # Gracefully skip rules that cannot evaluate

        return results


# Module-level singleton
expert_system = NutritionExpertSystem()


def analyse(totals, goals, user, water_ml, sugar_streak, meal_count, hour=20):
    """Convenience function: build WM and return list of feedback dicts."""
    wm = expert_system.build_working_memory(
        totals, goals, user, water_ml, sugar_streak, meal_count, hour
    )
    feedbacks = expert_system.evaluate(wm)
    return [f.to_dict() for f in feedbacks], wm
