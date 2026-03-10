# Components Workspace

A Flask-based workspace for tracking electronic components, prices, purchase dates, and links — with analytics, Excel export, login, and category grouping.

## Features
- Add/edit/delete components with price, quantity, bought date, and link.
- Category grouping with category suggestions (previously used categories).
- Analytics dashboard (totals, category spend, monthly spend, top purchases).
- Excel export (`/export`) with Components + Deleted sheets.
- Login required for all actions (role-based credentials in `pass.py`).
- IT role: Visitors page only. User role: Components + Analytics.
- Tracks and displays last login IP.
- Render-ready deployment.

## Tech Stack
- Python + Flask
- SQLite (local `components.db`)
- openpyxl (Excel export)

## Local Setup
```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5000`

## Background Run (no terminal block)
```bash
python run_server.py
```
Stop:
```bash
python stop_server.py
```

## Configuration
In `app.py`:
- `REQUIRE_LOGIN = True` to force login for all pages.

## Credentials (Role-Based)
Edit `pass.py` to set IT and User credentials.

Default (change these immediately):
- IT Username: `admin`
- IT Password: `admin123`
- User Username: `user`
- User Password: `user123`

Example:
```python
IT_USERNAME = "admin"
IT_PASSWORD_HASH = "pbkdf2:sha256:..."
USER_USERNAME = "user"
USER_PASSWORD_HASH = "pbkdf2:sha256:..."
```

To generate a hash:
```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your_password'))"
```

## Render Deployment
Render uses:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT`

A ready config file is included: `render.yaml`.

## Notes
- IP capture uses `ProxyFix` to work behind Render’s proxy.
- Database is local SQLite (`components.db`).

## License
Private / internal use.
