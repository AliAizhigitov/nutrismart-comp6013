# NutriSmart AI – Intelligent Nutrition Web Application
### COMP6013 Computing Project | Ali Aizhigitov (19271590)
### Supervisor: David Lightfoot | 2025–26

---

## Overview

NutriSmart AI is an advanced web-based dietary logging and intelligent feedback application that combines rule-based expert systems with machine learning features to provide comprehensive, personalized nutritional guidance.

## Setup & Installation

### Requirements
- Python 3.9+
- pip

### Quick Start
```bash
# 1. Extract project
cd nutrition_app

# 2. Install dependencies
pip install -r requirements.txt
# OR on Windows:
python -m pip install -r requirements.txt

# 3. Run application
python app.py
# Access at: http://localhost:5000
```

Database and food catalogue auto-initialize on first run.

---

## File Structure (2,000+ lines of code)

```
nutrition_app/
├── app.py (502 lines)          - Flask routes, auth, API endpoints
├── database.py (466 lines)     - SQLite schema, CRUD operations
├── expert_system.py (514 lines)- Rule-based inference engine
├── ai_features.py (320 lines)  - ML recommendation, prediction, anomaly detection
├── requirements.txt            - Dependencies (Flask, Werkzeug)
├── templates/ (11 files)
│   ├── base.html              - Navigation, footer, alerts
│   ├── index.html             - Landing page
│   ├── dashboard.html         - Main view with AI summary
│   ├── ai_recommendations.html- ML meal suggestions
│   ├── insights.html          - Expert system + predictions
│   ├── log_meal.html          - Food search + logging
│   ├── history.html           - 30-day table
│   ├── goals.html, profile.html, login.html, register.html
│   └── error.html
└── static/css/
    └── style.css (200 lines)   - Custom styling
```

---
