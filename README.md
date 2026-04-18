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

## Live Demo
https://aliaizhigitov.pythonanywhere.com

---
## File Structure (2,000+ lines of code)

```
nutrition_app/
├── app.py                 - Flask routes, auth, API endpoints
├── database.py            - SQLite schema, CRUD operations
├── expert_system.py       - Rule-based inference engine
├── ai_features.py         - ML recommendation, prediction, anomaly detection
├── requirements.txt       - Dependencies
├── nutrismart.db          - SQLite database
├── .env                   - API keys and configuration
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── ai_recommendations.html
│   ├── insights.html
│   ├── log_meal.html
│   ├── history.html
│   ├── goals.html
│   ├── profile.html
│   ├── login.html
│   ├── register.html
│   └── error.html
└── static/css/
    └── style.css
```

---
