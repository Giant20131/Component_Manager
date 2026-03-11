import os
import sqlite3
from datetime import datetime, date
from collections import OrderedDict
import importlib.util
import xml.etree.ElementTree as ET

from io import BytesIO

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
    send_file,
    Response,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook

app = Flask(__name__)
SECRET_KEY = "change-me-in-production"
app.secret_key = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

DB_PATH = os.path.join(app.root_path, "components.db")

# Feature flags
ENABLE_SIGNUP = False
REQUIRE_LOGIN = True
PUBLIC_HOMEPAGE = True
SITE_URL = ""
GOOGLE_SITE_VERIFICATION = ""
GOOGLE_VERIFICATION_FILENAME = "google7927882ddf10ea81.html"
GOOGLE_VERIFICATION_CONTENT = "google-site-verification: google7927882ddf10ea81.html"
CREDENTIALS_PATH = os.path.join(app.root_path, "pass.py")
ROLE_IT = "it"
ROLE_USER = "user"

SITEMAP_EXCLUDE_ENDPOINTS = {
    "static",
    "add_component",
    "edit_component",
    "delete_component",
    "export",
    "logout",
    "login",
    "register",
    "visitors",
    "analytics",
    "sitemap",
    "robots_txt",
    "google_verification_file",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_ip TEXT,
                last_login_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                bought_date TEXT NOT NULL,
                link TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                bought_date TEXT NOT NULL,
                link TEXT,
                deleted_reason TEXT NOT NULL,
                deleted_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                user_agent TEXT,
                username TEXT,
                visited_at TEXT NOT NULL
            )
            """
        )

        ensure_column(conn, "components", "link", "TEXT")
        ensure_column(conn, "deleted_components", "link", "TEXT")
        ensure_column(conn, "users", "last_login_ip", "TEXT")
        ensure_column(conn, "users", "last_login_at", "TEXT")
        ensure_column(conn, "visitors", "ip_address", "TEXT")
        ensure_column(conn, "visitors", "path", "TEXT")
        ensure_column(conn, "visitors", "method", "TEXT")
        ensure_column(conn, "visitors", "user_agent", "TEXT")
        ensure_column(conn, "visitors", "username", "TEXT")
        ensure_column(conn, "visitors", "visited_at", "TEXT")


def ensure_column(conn, table_name: str, column_name: str, column_type: str) -> None:
    existing = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if not any(row[1] == column_name for row in existing):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def load_credentials() -> dict[str, str]:
    if not os.path.exists(CREDENTIALS_PATH):
        raise RuntimeError("pass.py not found. Create pass.py with IT/USER credentials.")

    spec = importlib.util.spec_from_file_location("credentials", CREDENTIALS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pass.py.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    it_username = getattr(module, "IT_USERNAME", None)
    it_password_hash = getattr(module, "IT_PASSWORD_HASH", None)
    user_username = getattr(module, "USER_USERNAME", None)
    user_password_hash = getattr(module, "USER_PASSWORD_HASH", None)

    if not it_username or not it_password_hash or not user_username or not user_password_hash:
        raise RuntimeError(
            "pass.py must define IT_USERNAME, IT_PASSWORD_HASH, USER_USERNAME, USER_PASSWORD_HASH."
        )

    return {
        "it_username": str(it_username),
        "it_password_hash": str(it_password_hash),
        "user_username": str(user_username),
        "user_password_hash": str(user_password_hash),
    }


def get_client_ip() -> str:
    if request.access_route:
        return request.access_route[0]
    return request.remote_addr or "unknown"


def log_visit() -> None:
    if request.path.startswith("/static"):
        return
    if request.endpoint == "static":
        return

    ip = get_client_ip()
    now = datetime.utcnow().isoformat()
    ua = request.headers.get("User-Agent", "")
    username = session.get("username")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO visitors (ip_address, path, method, user_agent, username, visited_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ip, request.path, request.method, ua, username, now),
        )


def require_login_guard():
    if REQUIRE_LOGIN and not session.get("user_id"):
        return redirect(url_for("login", next=request.path))
    return None


def require_role(role: str):
    guard = require_login_guard()
    if guard:
        return guard
    if session.get("role") != role:
        abort(403)
    return None


@app.before_request
def before_request():
    init_db()
    log_visit()


@app.context_processor
def inject_flags():
    return {
        "ENABLE_SIGNUP": ENABLE_SIGNUP,
        "REQUIRE_LOGIN": REQUIRE_LOGIN,
        "current_user": session.get("username"),
        "last_login_ip": session.get("last_login_ip"),
        "last_login_at": session.get("last_login_at"),
        "current_role": session.get("role"),
        "google_site_verification": GOOGLE_SITE_VERIFICATION,
    }


@app.route("/")
def index():
    is_public_view = PUBLIC_HOMEPAGE and not session.get("user_id")
    if is_public_view:
        return render_template(
            "index.html",
            components=[],
            grouped_components=OrderedDict(),
            categories=[],
            total_price=0,
            today=date.today().isoformat(),
            is_public_view=True,
        )

    guard = require_login_guard()
    if guard:
        return guard
    role = session.get("role")
    if role == ROLE_IT:
        return redirect(url_for("visitors"))
    if role != ROLE_USER:
        abort(403)

    with get_db() as conn:
        components = conn.execute(
            """
            SELECT * FROM components
            ORDER BY COALESCE(category, ''), name, bought_date DESC
            """
        ).fetchall()
        categories = conn.execute(
            """
            SELECT DISTINCT category
            FROM components
            WHERE category IS NOT NULL AND TRIM(category) != ''
            ORDER BY category
            """
        ).fetchall()

    total_price = sum(row["price"] * row["quantity"] for row in components)
    today = date.today().isoformat()

    grouped = OrderedDict()
    for row in components:
        key = row["category"] or "Uncategorized"
        grouped.setdefault(key, []).append(row)

    return render_template(
        "index.html",
        components=components,
        grouped_components=grouped,
        categories=[row["category"] for row in categories],
        total_price=total_price,
        today=today,
        is_public_view=False,
    )


@app.route("/add", methods=["POST"])
def add_component():
    guard = require_role(ROLE_USER)
    if guard:
        return guard

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    price_raw = request.form.get("price", "0").strip()
    quantity_raw = request.form.get("quantity", "1").strip()
    bought_date = request.form.get("bought_date", "").strip() or date.today().isoformat()
    link = request.form.get("link", "").strip()

    if not name:
        flash("Component name is required.", "error")
        return redirect(url_for("index"))

    try:
        price = float(price_raw)
        quantity = int(quantity_raw)
        if price < 0 or quantity < 1:
            raise ValueError
    except ValueError:
        flash("Price must be a positive number and quantity must be at least 1.", "error")
        return redirect(url_for("index"))

    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO components (name, category, price, quantity, bought_date, link, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, category, price, quantity, bought_date, link or None, now, now),
        )

    flash("Component added.", "success")
    return redirect(url_for("index"))


@app.route("/edit/<int:component_id>", methods=["GET", "POST"])
def edit_component(component_id):
    guard = require_role(ROLE_USER)
    if guard:
        return guard

    with get_db() as conn:
        component = conn.execute(
            "SELECT * FROM components WHERE id = ?",
            (component_id,),
        ).fetchone()
        categories = conn.execute(
            """
            SELECT DISTINCT category
            FROM components
            WHERE category IS NOT NULL AND TRIM(category) != ''
            ORDER BY category
            """
        ).fetchall()

        if not component:
            abort(404)

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            price_raw = request.form.get("price", "0").strip()
            quantity_raw = request.form.get("quantity", "1").strip()
            bought_date = request.form.get("bought_date", "").strip() or date.today().isoformat()
            link = request.form.get("link", "").strip()

            if not name:
                flash("Component name is required.", "error")
                return redirect(url_for("edit_component", component_id=component_id))

            try:
                price = float(price_raw)
                quantity = int(quantity_raw)
                if price < 0 or quantity < 1:
                    raise ValueError
            except ValueError:
                flash("Price must be a positive number and quantity must be at least 1.", "error")
                return redirect(url_for("edit_component", component_id=component_id))

            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                UPDATE components
                SET name = ?, category = ?, price = ?, quantity = ?, bought_date = ?, link = ?, updated_at = ?
                WHERE id = ?
                """,
                (name, category, price, quantity, bought_date, link or None, now, component_id),
            )

            flash("Component updated.", "success")
            return redirect(url_for("index"))

    return render_template(
        "edit.html",
        component=component,
        categories=[row["category"] for row in categories],
    )


@app.route("/delete/<int:component_id>", methods=["POST"])
def delete_component(component_id):
    guard = require_role(ROLE_USER)
    if guard:
        return guard

    reason = request.form.get("delete_reason", "").strip()
    if not reason:
        flash("Delete reason is required.", "error")
        return redirect(url_for("index"))

    now = datetime.utcnow().isoformat()

    with get_db() as conn:
        component = conn.execute(
            "SELECT * FROM components WHERE id = ?",
            (component_id,),
        ).fetchone()

        if not component:
            flash("Component not found.", "error")
            return redirect(url_for("index"))

        conn.execute(
            """
            INSERT INTO deleted_components
            (component_id, name, category, price, quantity, bought_date, link, deleted_reason, deleted_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                component["id"],
                component["name"],
                component["category"],
                component["price"],
                component["quantity"],
                component["bought_date"],
                component["link"],
                reason,
                now,
                component["created_at"],
                component["updated_at"],
            ),
        )
        conn.execute("DELETE FROM components WHERE id = ?", (component_id,))

    flash("Component deleted.", "success")
    return redirect(url_for("index"))


@app.route("/analytics")
def analytics():
    guard = require_role(ROLE_USER)
    if guard:
        return guard

    with get_db() as conn:
        components = conn.execute("SELECT * FROM components").fetchall()

        total_spend = sum(row["price"] * row["quantity"] for row in components)
        total_components = len(components)
        total_quantity = sum(row["quantity"] for row in components) if components else 0
        deleted_count = conn.execute(
            "SELECT COUNT(*) AS count FROM deleted_components"
        ).fetchone()["count"]

        by_category = conn.execute(
            """
            SELECT COALESCE(category, 'Uncategorized') AS category,
                   SUM(price * quantity) AS total
            FROM components
            GROUP BY COALESCE(category, 'Uncategorized')
            ORDER BY total DESC
            """
        ).fetchall()

        by_month = conn.execute(
            """
            SELECT substr(bought_date, 1, 7) AS month,
                   SUM(price * quantity) AS total
            FROM components
            GROUP BY substr(bought_date, 1, 7)
            ORDER BY month DESC
            LIMIT 12
            """
        ).fetchall()

        top_expensive = conn.execute(
            """
            SELECT name, category, price, quantity, bought_date
            FROM components
            ORDER BY price * quantity DESC
            LIMIT 5
            """
        ).fetchall()

    max_category_total = max((row["total"] for row in by_category), default=0)
    max_month_total = max((row["total"] for row in by_month), default=0)

    return render_template(
        "analytics.html",
        total_spend=total_spend,
        total_components=total_components,
        total_quantity=total_quantity,
        deleted_count=deleted_count,
        by_category=by_category,
        by_month=by_month,
        top_expensive=top_expensive,
        max_category_total=max_category_total,
        max_month_total=max_month_total,
    )


@app.route("/export")
def export():
    guard = require_role(ROLE_USER)
    if guard:
        return guard

    with get_db() as conn:
        components = conn.execute("SELECT * FROM components ORDER BY bought_date DESC").fetchall()
        deleted = conn.execute("SELECT * FROM deleted_components ORDER BY deleted_at DESC").fetchall()

    wb = Workbook()
    ws_components = wb.active
    ws_components.title = "Components"
    ws_components.append(
        ["ID", "Name", "Category", "Price", "Quantity", "Bought Date", "Link", "Created At", "Updated At"]
    )
    for row in components:
        ws_components.append(
            [
                row["id"],
                row["name"],
                row["category"] or "Uncategorized",
                row["price"],
                row["quantity"],
                row["bought_date"],
                row["link"] or "",
                row["created_at"],
                row["updated_at"],
            ]
        )

    ws_deleted = wb.create_sheet(title="Deleted")
    ws_deleted.append(
        [
            "Deleted ID",
            "Original ID",
            "Name",
            "Category",
            "Price",
            "Quantity",
            "Bought Date",
            "Link",
            "Delete Reason",
            "Deleted At",
            "Created At",
            "Updated At",
        ]
    )
    for row in deleted:
        ws_deleted.append(
            [
                row["id"],
                row["component_id"],
                row["name"],
                row["category"] or "Uncategorized",
                row["price"],
                row["quantity"],
                row["bought_date"],
                row["link"] or "",
                row["deleted_reason"],
                row["deleted_at"],
                row["created_at"],
                row["updated_at"],
            ]
        )

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"components_export_{date.today().isoformat()}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if not ENABLE_SIGNUP:
        abort(404)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)
        now = datetime.utcnow().isoformat()

        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO users (username, password_hash, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (username, password_hash, now),
                )
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")
            return redirect(url_for("register"))

        flash("Account created. You can log in now.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        try:
            creds = load_credentials()
        except RuntimeError as exc:
            flash(str(exc), "error")
            return redirect(url_for("login"))

        role = None
        if username == creds["it_username"] and check_password_hash(
            creds["it_password_hash"], password
        ):
            role = ROLE_IT
        elif username == creds["user_username"] and check_password_hash(
            creds["user_password_hash"], password
        ):
            role = ROLE_USER
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))

        client_ip = get_client_ip()
        now = datetime.utcnow().isoformat()
        session["user_id"] = 1 if role == ROLE_IT else 2
        session["username"] = username
        session["role"] = role
        session["last_login_ip"] = client_ip
        session["last_login_at"] = now

        next_url = request.args.get("next") or url_for("index")
        return redirect(next_url)

    return render_template("login.html", current_ip=get_client_ip())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/visitors")
def visitors():
    guard = require_role(ROLE_IT)
    if guard:
        return guard

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, ip_address, path, method, user_agent, username, visited_at
            FROM visitors
            ORDER BY visited_at DESC
            """
        ).fetchall()

    return render_template("visitors.html", visitors=rows)


def get_base_url() -> str:
    if SITE_URL:
        return SITE_URL
    return request.url_root.rstrip("/")


def is_sitemap_eligible(rule) -> bool:
    if "GET" not in rule.methods:
        return False
    if rule.endpoint in SITEMAP_EXCLUDE_ENDPOINTS:
        return False
    if rule.rule.startswith("/static"):
        return False
    if rule.arguments:
        return False
    if rule.endpoint == "register" and not ENABLE_SIGNUP:
        return False
    if rule.endpoint == "index" and not PUBLIC_HOMEPAGE:
        return False
    return True


@app.route("/sitemap.xml")
def sitemap():
    base_url = get_base_url()
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    today = date.today().isoformat()

    for rule in app.url_map.iter_rules():
        if not is_sitemap_eligible(rule):
            continue
        loc = f"{base_url}{url_for(rule.endpoint)}"
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = loc
        ET.SubElement(url_el, "lastmod").text = today

    xml_bytes = ET.tostring(urlset, encoding="utf-8", xml_declaration=True)
    return Response(xml_bytes, mimetype="application/xml")


@app.route("/robots.txt")
def robots_txt():
    base_url = get_base_url()
    sitemap_url = f"{base_url}{url_for('sitemap')}"
    content = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    return Response(content, mimetype="text/plain")


@app.route(f"/{GOOGLE_VERIFICATION_FILENAME}")
def google_verification_file():
    return Response(GOOGLE_VERIFICATION_CONTENT, mimetype="text/plain")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
