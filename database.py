"""
database.py - Database initialisation and helper functions for NutriSmart.

Uses SQLite via the built-in sqlite3 module; no ORM dependency required.
All helper functions return plain dicts / lists so views stay clean.
"""

import sqlite3
import os
from datetime import date, datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "nutrismart.db")


# ─────────────────────────────────────────────
#  Connection factory
# ─────────────────────────────────────────────

def get_db():
    """Return a connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
#  Schema creation
# ─────────────────────────────────────────────

def init_db():
    """Create all tables if they do not exist."""
    conn = get_db()
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    NOT NULL UNIQUE,
                email       TEXT    NOT NULL UNIQUE,
                password_hash TEXT  NOT NULL,
                full_name   TEXT,
                age         INTEGER,
                weight_kg   REAL,
                height_cm   REAL,
                gender      TEXT    CHECK(gender IN ('male','female','other')),
                activity_level TEXT DEFAULT 'moderate'
                                    CHECK(activity_level IN ('sedentary','light','moderate','active','very_active')),
                created_at  TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS goals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                calories_target INTEGER DEFAULT 2000,
                protein_target  REAL    DEFAULT 50,
                carbs_target    REAL    DEFAULT 250,
                fat_target      REAL    DEFAULT 70,
                sugar_limit     REAL    DEFAULT 50,
                sodium_limit    REAL    DEFAULT 2300,
                fiber_target    REAL    DEFAULT 25,
                water_target_ml INTEGER DEFAULT 2000,
                updated_at      TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS meal_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_date    TEXT    NOT NULL DEFAULT (date('now')),
                meal_type   TEXT    NOT NULL
                                    CHECK(meal_type IN ('breakfast','lunch','dinner','snack')),
                food_name   TEXT    NOT NULL,
                quantity_g  REAL    NOT NULL DEFAULT 100,
                calories    REAL    NOT NULL DEFAULT 0,
                protein_g   REAL    NOT NULL DEFAULT 0,
                carbs_g     REAL    NOT NULL DEFAULT 0,
                fat_g       REAL    NOT NULL DEFAULT 0,
                sugar_g     REAL    NOT NULL DEFAULT 0,
                fiber_g     REAL    NOT NULL DEFAULT 0,
                sodium_mg   REAL    NOT NULL DEFAULT 0,
                notes       TEXT,
                logged_at   TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS water_logs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_date    TEXT    NOT NULL DEFAULT (date('now')),
                amount_ml   INTEGER NOT NULL,
                logged_at   TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS feedback_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_date    TEXT    NOT NULL DEFAULT (date('now')),
                rule_id     TEXT    NOT NULL,
                severity    TEXT    CHECK(severity IN ('info','warning','danger')),
                message     TEXT    NOT NULL,
                generated_at TEXT   DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS foods (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                category    TEXT,
                calories_per_100g  REAL DEFAULT 0,
                protein_per_100g   REAL DEFAULT 0,
                carbs_per_100g     REAL DEFAULT 0,
                fat_per_100g       REAL DEFAULT 0,
                sugar_per_100g     REAL DEFAULT 0,
                fiber_per_100g     REAL DEFAULT 0,
                sodium_per_100g    REAL DEFAULT 0
            );
        """)
    conn.close()


# ─────────────────────────────────────────────
#  User helpers
# ─────────────────────────────────────────────

def create_user(username, email, password_hash, full_name=""):
    conn = get_db()
    with conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password_hash, full_name) VALUES (?,?,?,?)",
            (username, email, password_hash, full_name)
        )
        user_id = cur.lastrowid
        # Create default goals
        conn.execute("INSERT INTO goals (user_id) VALUES (?)", (user_id,))
    conn.close()
    return user_id


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_username(username):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(user) if user else None


def update_user_profile(user_id, **kwargs):
    allowed = {'full_name', 'age', 'weight_kg', 'height_cm', 'gender', 'activity_level'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    conn = get_db()
    with conn:
        conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    conn.close()


# ─────────────────────────────────────────────
#  Goals helpers
# ─────────────────────────────────────────────

def get_goals(user_id):
    conn = get_db()
    goals = conn.execute("SELECT * FROM goals WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(goals) if goals else None


def update_goals(user_id, **kwargs):
    allowed = {
        'calories_target', 'protein_target', 'carbs_target', 'fat_target',
        'sugar_limit', 'sodium_limit', 'fiber_target', 'water_target_ml'
    }
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    fields['updated_at'] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    conn = get_db()
    with conn:
        conn.execute(f"UPDATE goals SET {set_clause} WHERE user_id = ?", values)
    conn.close()


# ─────────────────────────────────────────────
#  Meal log helpers
# ─────────────────────────────────────────────

def add_meal(user_id, meal_type, food_name, quantity_g,
             calories, protein_g, carbs_g, fat_g, sugar_g, fiber_g, sodium_mg,
             log_date=None, notes=""):
    log_date = log_date or date.today().isoformat()
    conn = get_db()
    with conn:
        conn.execute("""
            INSERT INTO meal_logs
            (user_id, log_date, meal_type, food_name, quantity_g,
             calories, protein_g, carbs_g, fat_g, sugar_g, fiber_g, sodium_mg, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (user_id, log_date, meal_type, food_name, quantity_g,
              calories, protein_g, carbs_g, fat_g, sugar_g, fiber_g, sodium_mg, notes))
    conn.close()


def delete_meal(meal_id, user_id):
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM meal_logs WHERE id = ? AND user_id = ?", (meal_id, user_id))
    conn.close()


def get_meals_for_date(user_id, log_date):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM meal_logs WHERE user_id = ? AND log_date = ? ORDER BY meal_type, logged_at",
        (user_id, log_date)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_totals(user_id, log_date):
    conn = get_db()
    row = conn.execute("""
        SELECT
            COALESCE(SUM(calories), 0)   AS calories,
            COALESCE(SUM(protein_g), 0)  AS protein_g,
            COALESCE(SUM(carbs_g), 0)    AS carbs_g,
            COALESCE(SUM(fat_g), 0)      AS fat_g,
            COALESCE(SUM(sugar_g), 0)    AS sugar_g,
            COALESCE(SUM(fiber_g), 0)    AS fiber_g,
            COALESCE(SUM(sodium_mg), 0)  AS sodium_mg
        FROM meal_logs
        WHERE user_id = ? AND log_date = ?
    """, (user_id, log_date)).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_weekly_summary(user_id, end_date=None):
    """Return per-day totals for the 7 days ending on end_date (inclusive)."""
    if end_date is None:
        end_date = date.today()
    elif isinstance(end_date, str):
        end_date = date.fromisoformat(end_date)
    start_date = end_date - timedelta(days=6)
    conn = get_db()
    rows = conn.execute("""
        SELECT
            log_date,
            COALESCE(SUM(calories), 0)  AS calories,
            COALESCE(SUM(protein_g), 0) AS protein_g,
            COALESCE(SUM(carbs_g), 0)   AS carbs_g,
            COALESCE(SUM(fat_g), 0)     AS fat_g,
            COALESCE(SUM(sugar_g), 0)   AS sugar_g,
            COALESCE(SUM(fiber_g), 0)   AS fiber_g,
            COALESCE(SUM(sodium_mg), 0) AS sodium_mg
        FROM meal_logs
        WHERE user_id = ?
          AND log_date BETWEEN ? AND ?
        GROUP BY log_date
        ORDER BY log_date
    """, (user_id, start_date.isoformat(), end_date.isoformat())).fetchall()
    conn.close()
    # Fill in missing dates with zeros
    data = {r['log_date']: dict(r) for r in rows}
    result = []
    for i in range(7):
        d = (start_date + timedelta(days=i)).isoformat()
        result.append(data.get(d, {
            'log_date': d, 'calories': 0, 'protein_g': 0,
            'carbs_g': 0, 'fat_g': 0, 'sugar_g': 0,
            'fiber_g': 0, 'sodium_mg': 0
        }))
    return result


def get_sugar_streak(user_id, sugar_limit, days=3):
    """Return the number of consecutive days (up to `days`) sugar exceeded limit."""
    conn = get_db()
    count = 0
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        row = conn.execute(
            "SELECT COALESCE(SUM(sugar_g),0) AS s FROM meal_logs WHERE user_id=? AND log_date=?",
            (user_id, d)
        ).fetchone()
        if row and row['s'] > sugar_limit:
            count += 1
        else:
            break
    conn.close()
    return count


# ─────────────────────────────────────────────
#  Water log helpers
# ─────────────────────────────────────────────

def add_water(user_id, amount_ml, log_date=None):
    log_date = log_date or date.today().isoformat()
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO water_logs (user_id, log_date, amount_ml) VALUES (?,?,?)",
            (user_id, log_date, amount_ml)
        )
    conn.close()


def get_water_for_date(user_id, log_date):
    conn = get_db()
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_ml), 0) AS total FROM water_logs WHERE user_id=? AND log_date=?",
        (user_id, log_date)
    ).fetchone()
    conn.close()
    return row['total'] if row else 0


# ─────────────────────────────────────────────
#  Feedback log helpers
# ─────────────────────────────────────────────

def save_feedback(user_id, feedbacks, log_date=None):
    log_date = log_date or date.today().isoformat()
    if not feedbacks:
        return
    conn = get_db()
    with conn:
        # Clear today's feedback before re-inserting
        conn.execute(
            "DELETE FROM feedback_log WHERE user_id=? AND log_date=?",
            (user_id, log_date)
        )
        conn.executemany("""
            INSERT INTO feedback_log (user_id, log_date, rule_id, severity, message)
            VALUES (?,?,?,?,?)
        """, [(user_id, log_date, f['rule_id'], f['severity'], f['message']) for f in feedbacks])
    conn.close()


def get_feedback_for_date(user_id, log_date):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM feedback_log WHERE user_id=? AND log_date=? ORDER BY severity DESC",
        (user_id, log_date)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  Food database helpers
# ─────────────────────────────────────────────

def search_foods(query, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM foods WHERE name LIKE ? LIMIT ?",
        (f"%{query}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_food_by_id(food_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM foods WHERE id=?", (food_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def seed_food_database():
    """Insert a curated food database (runs only if table is empty)."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0]
    if count > 0:
        conn.close()
        return

    foods = [
        # (name, category, cal, prot, carbs, fat, sugar, fiber, sodium)
        ("Chicken Breast (grilled)", "Meat & Poultry", 165, 31, 0, 3.6, 0, 0, 74),
        ("Salmon (baked)", "Fish & Seafood", 208, 20, 0, 13, 0, 0, 59),
        ("Tuna (canned in water)", "Fish & Seafood", 116, 25.5, 0, 0.8, 0, 0, 320),
        ("Egg (boiled)", "Dairy & Eggs", 155, 13, 1.1, 11, 1.1, 0, 124),
        ("Whole Milk", "Dairy & Eggs", 61, 3.2, 4.8, 3.3, 5.1, 0, 44),
        ("Greek Yogurt (plain)", "Dairy & Eggs", 59, 10, 3.6, 0.4, 3.2, 0, 36),
        ("Cheddar Cheese", "Dairy & Eggs", 402, 25, 1.3, 33, 0.5, 0, 621),
        ("White Rice (cooked)", "Grains & Cereals", 130, 2.7, 28, 0.3, 0, 0.4, 1),
        ("Brown Rice (cooked)", "Grains & Cereals", 112, 2.6, 24, 0.9, 0, 1.8, 5),
        ("Oats (dry)", "Grains & Cereals", 389, 17, 66, 7, 0, 10.6, 2),
        ("Wholemeal Bread (1 slice)", "Grains & Cereals", 81, 4, 15, 1, 1.5, 1.9, 172),
        ("White Bread (1 slice)", "Grains & Cereals", 79, 2.7, 15, 1, 1.6, 0.6, 152),
        ("Pasta (cooked)", "Grains & Cereals", 131, 5, 25, 1.1, 0.6, 1.8, 1),
        ("Banana", "Fruit", 89, 1.1, 23, 0.3, 12, 2.6, 1),
        ("Apple", "Fruit", 52, 0.3, 14, 0.2, 10, 2.4, 1),
        ("Orange", "Fruit", 47, 0.9, 12, 0.1, 9.4, 2.4, 0),
        ("Strawberries", "Fruit", 32, 0.7, 7.7, 0.3, 4.9, 2, 1),
        ("Blueberries", "Fruit", 57, 0.7, 14, 0.3, 10, 2.4, 1),
        ("Grapes", "Fruit", 69, 0.7, 18, 0.2, 15, 0.9, 2),
        ("Broccoli (steamed)", "Vegetables", 35, 2.4, 7.2, 0.4, 1.7, 2.6, 33),
        ("Spinach (raw)", "Vegetables", 23, 2.9, 3.6, 0.4, 0.4, 2.2, 79),
        ("Carrots (raw)", "Vegetables", 41, 0.9, 10, 0.2, 4.7, 2.8, 69),
        ("Sweet Potato (baked)", "Vegetables", 90, 2, 21, 0.1, 6.5, 3.3, 36),
        ("Tomato (raw)", "Vegetables", 18, 0.9, 3.9, 0.2, 2.6, 1.2, 5),
        ("Avocado", "Vegetables", 160, 2, 9, 15, 0.7, 6.7, 7),
        ("Almonds", "Nuts & Seeds", 579, 21, 22, 50, 4.4, 12.5, 1),
        ("Peanut Butter", "Nuts & Seeds", 588, 25, 20, 50, 9, 6, 459),
        ("Walnuts", "Nuts & Seeds", 654, 15, 14, 65, 2.6, 6.7, 2),
        ("Lentils (cooked)", "Legumes", 116, 9, 20, 0.4, 1.8, 7.9, 2),
        ("Chickpeas (cooked)", "Legumes", 164, 8.9, 27, 2.6, 4.8, 7.6, 7),
        ("Black Beans (cooked)", "Legumes", 132, 8.9, 24, 0.5, 0.3, 8.7, 1),
        ("Tofu (firm)", "Legumes", 76, 8, 1.9, 4.8, 0.9, 0.3, 7),
        ("Coca-Cola (330ml can)", "Beverages", 139, 0, 35, 0, 35, 0, 44),
        ("Orange Juice", "Beverages", 45, 0.7, 10, 0.2, 8.4, 0.2, 1),
        ("Coffee (black, unsweetened)", "Beverages", 2, 0.3, 0, 0, 0, 0, 5),
        ("Butter", "Fats & Oils", 717, 0.9, 0.1, 81, 0.1, 0, 643),
        ("Olive Oil", "Fats & Oils", 884, 0, 0, 100, 0, 0, 2),
        ("Protein Shake (whey)", "Supplements", 400, 80, 20, 5, 5, 0, 200),
        ("Chocolate Bar (milk)", "Snacks & Sweets", 535, 7.7, 59, 30, 52, 1.5, 79),
        ("Crisps / Potato Chips", "Snacks & Sweets", 536, 7, 53, 34, 0.4, 4.4, 534),
        ("Pizza (cheese, 1 slice)", "Fast Food", 266, 11, 33, 10, 3.6, 2.3, 551),
        ("Hamburger", "Fast Food", 295, 17, 24, 14, 5, 1.3, 396),
        ("French Fries", "Fast Food", 312, 3.4, 41, 15, 0.3, 3.8, 210),
        ("Sausage", "Meat & Poultry", 301, 11, 1.5, 27, 0, 0, 780),
        ("Bacon (grilled)", "Meat & Poultry", 541, 37, 1.4, 42, 0, 0, 1717),
        ("Beef Mince (lean, cooked)", "Meat & Poultry", 215, 26, 0, 12, 0, 0, 75),
        ("Kidney Beans (cooked)", "Legumes", 127, 8.7, 23, 0.5, 0.3, 7.4, 2),
        ("Cottage Cheese", "Dairy & Eggs", 98, 11, 3.4, 4.3, 2.7, 0, 364),
        ("Hummus", "Legumes", 177, 7.9, 14, 10, 1.4, 6, 379),
        ("Quinoa (cooked)", "Grains & Cereals", 120, 4.4, 22, 1.9, 0.9, 2.8, 7),
        ("Mango", "Fruit", 60, 0.8, 15, 0.4, 14, 1.6, 1),
        ("Pineapple", "Fruit", 50, 0.5, 13, 0.1, 10, 1.4, 1),
        ("Watermelon", "Fruit", 30, 0.6, 7.6, 0.2, 6.2, 0.4, 1),
        ("Kale (raw)", "Vegetables", 49, 4.3, 9, 0.9, 2.3, 3.6, 38),
        ("Cucumber (raw)", "Vegetables", 15, 0.7, 3.6, 0.1, 1.7, 0.5, 2),
        ("Bell Pepper (red)", "Vegetables", 31, 1, 6, 0.3, 4.2, 2.1, 4),
        ("Mushrooms (raw)", "Vegetables", 22, 3.1, 3.3, 0.3, 2, 1, 5),
        ("Onion (raw)", "Vegetables", 40, 1.1, 9.3, 0.1, 4.2, 1.7, 4),
        ("Garlic", "Vegetables", 149, 6.4, 33, 0.5, 1, 2.1, 17),
        ("Pear", "Fruit", 57, 0.4, 15, 0.1, 9.8, 3.1, 1),
        ("Peach", "Fruit", 39, 0.9, 10, 0.3, 8.4, 1.5, 0),
        ("Dark Chocolate (70%+)", "Snacks & Sweets", 598, 7.8, 46, 43, 24, 10.9, 20),
    ]
    with conn:
        conn.executemany("""
            INSERT INTO foods (name, category, calories_per_100g, protein_per_100g,
            carbs_per_100g, fat_per_100g, sugar_per_100g, fiber_per_100g, sodium_per_100g)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, foods)
    conn.close()
