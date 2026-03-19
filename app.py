from flask import Flask, render_template, request, redirect, url_for, session, Response
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import DataPoint
import io
import sqlite3
from datetime import datetime, timedelta
import requests
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ================= CONFIG =================
app.secret_key = os.environ.get("SECRET_KEY", "o'zgartiring-bu-qiymatni")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8588085417:AAG1_uFr9irp7-E2fGd20jg0BbxxUopSsH4")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5703562662")


# ================= TELEGRAM =================
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram token yoki chat_id yo'q!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload, timeout=5)
        if not response.json().get("ok"):
            print("Telegram xato javobi:", response.text)
    except Exception as e:
        print("Telegram xato:", e)


# ================= DATABASE =================
def get_db():
    # Render da /data papkasi persistent disk, localda oddiy fayl
    db_path = "/data/users.db" if os.path.exists("/data") else "users.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        company_id INTEGER,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        balance INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # user_id ustuni qo'shildi (avvalgi versiyada yo'q edi — bug)
    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        user_id INTEGER,
        amount INTEGER,
        description TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message TEXT,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS workers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT,
        position TEXT,
        phone TEXT,
        company_id INTEGER,
        status TEXT DEFAULT 'active',
        monthly_salary INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS salaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER,
        company_id INTEGER,
        amount INTEGER,
        note TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER,
        company_id INTEGER,
        date TEXT,
        status TEXT DEFAULT 'present',
        note TEXT,
        created_at TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS advances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER,
        company_id INTEGER,
        amount INTEGER,
        note TEXT,
        created_at TEXT
    )
    """)

    # monthly_salary ustunini mavjud workers jadvaliga qo'shish (migration)
    try:
        c.execute("ALTER TABLE workers ADD COLUMN status TEXT DEFAULT 'active'")
    except:
        pass
    try:
        c.execute("ALTER TABLE workers ADD COLUMN monthly_salary INTEGER DEFAULT 0")
    except:
        pass

    # Default admin: parol hash qilingan holda saqlanadi
    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchone():
        c.execute("""
            INSERT INTO users (username, password, role, created_at)
            VALUES ('admin', ?, 'admin', ?)
        """, (
            generate_password_hash("Admin@12345"),  # Kuchli default parol
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    conn.commit()
    conn.close()


# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT id, username, password, role, company_id FROM users WHERE username=?",
            (username,)
        )
        user = c.fetchone()
        conn.close()

        # check_password_hash — parolni xavfsiz tekshiradi
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user"] = user["username"]
            session["role"] = user["role"]
            session["company_id"] = user["company_id"]
            return redirect(url_for("dashboard"))
        else:
            error = "Login yoki parol noto'g'ri!"

    return render_template("login.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            error = "Username va parol bo'sh bo'lishi mumkin emas!"
            return render_template("signup.html", error=error)

        if len(password) < 6:
            error = "Parol kamida 6 ta belgidan iborat bo'lishi kerak!"
            return render_template("signup.html", error=error)

        try:
            conn = get_db()
            c = conn.cursor()
            c.execute("""
                INSERT INTO users (username, password, role, created_at)
                VALUES (?, ?, 'director', ?)
            """, (
                username,
                generate_password_hash(password),  # Parol hash qilinadi
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            error = "Bu login mavjud!"
        except Exception as e:
            print("Signup xato:", e)
            error = "Xatolik yuz berdi, qayta urinib ko'ring."

    return render_template("signup.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()

    role = session.get("role")
    username = session.get("user")

    period = request.args.get("period")
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    total_balance = 0
    total_expenses = 0
    profit = 0
    companies_count = 0
    labels = []
    values = []
    warning = None

    # ================= ADMIN =================
    if role == "admin":
        c.execute("SELECT IFNULL(SUM(balance),0) FROM companies")
        total_balance = c.fetchone()[0]

        c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses")
        total_expenses = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM companies")
        companies_count = c.fetchone()[0]

        profit = total_balance

        if period == "day":
            c.execute("""
                SELECT strftime('%H', created_at), SUM(amount)
                FROM expenses
                WHERE date(created_at)=date('now')
                GROUP BY strftime('%H', created_at)
            """)
            data = c.fetchall()
            labels = [f"{row[0]}:00" for row in data]
            values = [row[1] for row in data]

        elif period == "month":
            c.execute("""
                SELECT date(created_at), SUM(amount)
                FROM expenses
                WHERE strftime('%Y-%m', created_at)=strftime('%Y-%m','now')
                GROUP BY date(created_at)
            """)
            data = c.fetchall()
            labels = [row[0] for row in data]
            values = [row[1] for row in data]

        elif period == "year":
            c.execute("""
                SELECT strftime('%Y-%m', created_at), SUM(amount)
                FROM expenses
                WHERE strftime('%Y', created_at)=strftime('%Y','now')
                GROUP BY strftime('%Y-%m', created_at)
            """)
            data = c.fetchall()
            labels = [row[0] for row in data]
            values = [row[1] for row in data]

        elif date_from and date_to:
            c.execute("""
                SELECT date(created_at), SUM(amount)
                FROM expenses
                WHERE date(created_at) BETWEEN ? AND ?
                GROUP BY date(created_at)
            """, (date_from, date_to))
            data = c.fetchall()
            labels = [row[0] for row in data]
            values = [row[1] for row in data]

        else:
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                c.execute(
                    "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE date(created_at)=?",
                    (day,)
                )
                labels.append(day)
                values.append(c.fetchone()[0])

    # ================= DIRECTOR =================
    else:
        c.execute(
            "SELECT company_id FROM users WHERE username=?",
            (username,)
        )
        row = c.fetchone()

        if not row or not row["company_id"]:
            warning = "Siz kompaniyaga biriktirilmagansiz"
        else:
            company_id = row["company_id"]

            c.execute(
                "SELECT IFNULL(balance,0) FROM companies WHERE id=?",
                (company_id,)
            )
            total_balance = c.fetchone()[0]

            c.execute(
                "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=?",
                (company_id,)
            )
            total_expenses = c.fetchone()[0]

            profit = total_balance - total_expenses
            companies_count = 1

            if period == "day":
                c.execute("""
                    SELECT strftime('%H', created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND date(created_at)=date('now')
                    GROUP BY strftime('%H', created_at)
                """, (company_id,))
                data = c.fetchall()
                labels = [f"{row[0]}:00" for row in data]
                values = [row[1] for row in data]

            elif period == "month":
                c.execute("""
                    SELECT date(created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND strftime('%Y-%m', created_at)=strftime('%Y-%m','now')
                    GROUP BY date(created_at)
                """, (company_id,))
                data = c.fetchall()
                labels = [row[0] for row in data]
                values = [row[1] for row in data]

            elif period == "year":
                c.execute("""
                    SELECT strftime('%Y-%m', created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND strftime('%Y', created_at)=strftime('%Y','now')
                    GROUP BY strftime('%Y-%m', created_at)
                """, (company_id,))
                data = c.fetchall()
                labels = [row[0] for row in data]
                values = [row[1] for row in data]

            elif date_from and date_to:
                c.execute("""
                    SELECT date(created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND date(created_at) BETWEEN ? AND ?
                    GROUP BY date(created_at)
                """, (company_id, date_from, date_to))
                data = c.fetchall()
                labels = [row[0] for row in data]
                values = [row[1] for row in data]

            else:
                for i in range(6, -1, -1):
                    day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                    c.execute(
                        """SELECT IFNULL(SUM(amount),0)
                           FROM expenses
                           WHERE company_id=? AND date(created_at)=?""",
                        (company_id, day)
                    )
                    labels.append(day)
                    values.append(c.fetchone()[0])

    conn.close()

    return render_template(
        "dashboard.html",
        total_balance=total_balance,
        total_expenses=total_expenses,
        profit=profit,
        companies_count=companies_count,
        labels=labels,
        values=values,
        warning=warning
    )


# ================= ADMIN : COMPANIES =================
@app.route("/admin/companies", methods=["GET", "POST"])
def admin_companies():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        balance = int(request.form.get("balance", 0))

        if name:
            c.execute(
                "INSERT INTO companies (name, balance, created_at) VALUES (?, ?, ?)",
                (name, balance, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            conn.commit()

        conn.close()
        return redirect(url_for("admin_companies"))

    c.execute("""
        SELECT
            c.id,
            c.name,
            c.balance,
            u.username AS director,
            IFNULL(SUM(e.amount), 0) AS total_expense
        FROM companies c
        LEFT JOIN users u ON u.company_id = c.id AND u.role = 'director'
        LEFT JOIN expenses e ON e.company_id = c.id
        GROUP BY c.id
        ORDER BY c.id DESC
    """)
    companies = c.fetchall()
    conn.close()

    return render_template("admin_companies.html", companies=companies)


# ================= EXPENSES (DIRECTOR) =================
@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    if "user" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "director":
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT id, company_id FROM users WHERE username=?",
        (session["user"],)
    )
    user_row = c.fetchone()

    if not user_row or not user_row["company_id"]:
        conn.close()
        return render_template(
            "expenses.html",
            expenses=[],
            balance=0,
            error="Siz kompaniyaga biriktirilmagansiz ❌"
        )

    user_id = user_row["id"]
    company_id = user_row["company_id"]

    if request.method == "POST":
        try:
            amount = int(request.form.get("amount", 0))
        except ValueError:
            amount = 0

        description = request.form.get("description", "").strip()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        c.execute(
            "SELECT balance, name FROM companies WHERE id=?",
            (company_id,)
        )
        company_row = c.fetchone()
        balance = company_row["balance"]
        company_name = company_row["name"]

        if amount <= 0:
            conn.close()
            return render_template(
                "expenses.html",
                expenses=[],
                balance=balance,
                error="Xarajat summasi noto'g'ri ❌"
            )

        if amount > balance:
            conn.close()
            return render_template(
                "expenses.html",
                expenses=[],
                balance=balance,
                error="Balans yetarli emas ❌"
            )

        # user_id ham yoziladi (tuzatildi)
        c.execute("""
            INSERT INTO expenses (company_id, user_id, amount, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (company_id, user_id, amount, description, created_at))

        c.execute(
            "UPDATE companies SET balance = balance - ? WHERE id=?",
            (amount, company_id)
        )

        conn.commit()

        message = f"""
<b>💸 Yangi xarajat</b>
🏢 Kompaniya: <b>{company_name}</b>
👔 Direktor: <b>{session['user']}</b>
💰 Summa: <b>{amount:,} so'm</b>
📝 Izoh: {description}
🕒 Sana: {created_at}
"""
        send_telegram_message(message)

        conn.close()
        return redirect(url_for("expenses"))

    c.execute("""
        SELECT amount, description, created_at
        FROM expenses
        WHERE company_id=?
        ORDER BY id DESC
    """, (company_id,))
    expense_list = c.fetchall()

    c.execute(
        "SELECT balance FROM companies WHERE id=?",
        (company_id,)
    )
    balance = c.fetchone()["balance"]

    conn.close()

    return render_template(
        "expenses.html",
        expenses=expense_list,
        balance=balance,
        error=None
    )


# ================= ADMIN : DIRECTOR DETAIL =================
@app.route("/admin/director/<int:director_id>", methods=["GET", "POST"])
def admin_director_detail(director_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            u.id,
            u.username,
            u.created_at,
            c.name AS company,
            c.id AS company_id_val
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.id = ?
    """, (director_id,))
    director = c.fetchone()

    if not director:
        conn.close()
        return "Direktor topilmadi ❌"

    if request.method == "POST":
        company_id = request.form.get("company_id")
        if company_id:
            c.execute(
                "UPDATE users SET company_id=? WHERE id=?",
                (company_id, director_id)
            )
            conn.commit()
        conn.close()
        return redirect(url_for("admin_director_detail", director_id=director_id))

    c.execute("SELECT id, name FROM companies")
    companies = c.fetchall()

    company_balance = 0
    total_expenses = 0
    recent_expenses = []
    chart_labels = []
    chart_values = []

    if director["company_id_val"]:
        c.execute("SELECT balance FROM companies WHERE id=?", (director["company_id_val"],))
        row = c.fetchone()
        if row:
            company_balance = row["balance"]

        c.execute("SELECT IFNULL(SUM(amount), 0) FROM expenses WHERE company_id=?", (director["company_id_val"],))
        total_expenses = c.fetchone()[0]

        # Oxirgi 10 ta xarajat
        c.execute("""
            SELECT amount, description, created_at
            FROM expenses WHERE company_id=?
            ORDER BY id DESC LIMIT 10
        """, (director["company_id_val"],))
        recent_expenses = c.fetchall()

        # Oxirgi 7 kunlik grafik
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=? AND date(created_at)=?",
                      (director["company_id_val"], day))
            chart_labels.append(day[-5:])
            chart_values.append(c.fetchone()[0])

    conn.close()

    return render_template(
        "admin_director_detail.html",
        director=director,
        companies=companies,
        company_balance=company_balance,
        total_expenses=total_expenses,
        recent_expenses=recent_expenses,
        chart_labels=chart_labels,
        chart_values=chart_values
    )


# ================= ADMIN : DIRECTORS =================
@app.route("/admin/directors")
def admin_directors():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            u.id,
            u.username,
            c.name AS company,
            u.created_at
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.role = 'director'
        ORDER BY u.id DESC
    """)
    directors = c.fetchall()
    conn.close()

    return render_template("admin_directors.html", directors=directors)


# ================= ADMIN : COMPANY DETAIL =================
@app.route("/admin/company/<int:company_id>")
def admin_company_detail(company_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "SELECT id, name, balance, created_at FROM companies WHERE id=?",
        (company_id,)
    )
    company = c.fetchone()
    if not company:
        conn.close()
        return "Kompaniya topilmadi ❌"

    c.execute(
        "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=?",
        (company_id,)
    )
    total_expenses = c.fetchone()[0]

    # Tuzatildi: har bir direktor o'zining xarajatlarini ko'rsatadi
    c.execute("""
        SELECT
            u.id,
            u.username,
            IFNULL(SUM(e.amount),0) AS total
        FROM users u
        LEFT JOIN expenses e ON e.user_id = u.id
        WHERE u.company_id=? AND u.role='director'
        GROUP BY u.id
    """, (company_id,))
    directors = c.fetchall()

    period = request.args.get("period")
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    query = """
        SELECT
            u.username,
            e.amount,
            e.description,
            e.created_at
        FROM expenses e
        LEFT JOIN users u ON u.id = e.user_id
        WHERE e.company_id=?
    """
    params = [company_id]

    if period == "day":
        query += " AND date(e.created_at)=date('now')"
    elif period == "month":
        query += " AND strftime('%Y-%m', e.created_at)=strftime('%Y-%m','now')"
    elif from_date and to_date:
        query += " AND date(e.created_at) BETWEEN ? AND ?"
        params.extend([from_date, to_date])

    query += " ORDER BY e.created_at DESC"
    c.execute(query, params)
    expense_list = c.fetchall()

    # Oxirgi 7 kunlik grafik
    chart_labels = []
    chart_values = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        c.execute(
            "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=? AND date(created_at)=?",
            (company_id, day)
        )
        chart_labels.append(day[-5:])
        chart_values.append(c.fetchone()[0])

    # Oylik xarajatlar (oxirgi 6 oy)
    c.execute("""
        SELECT strftime('%Y-%m', created_at) as month, IFNULL(SUM(amount),0)
        FROM expenses WHERE company_id=?
        GROUP BY month ORDER BY month DESC LIMIT 6
    """, (company_id,))
    monthly = c.fetchall()

    # Balans to'ldirish uchun POST
    conn.close()

    return render_template(
        "admin_company_detail.html",
        company=company,
        total_expenses=total_expenses,
        directors=directors,
        expenses=expense_list,
        chart_labels=chart_labels,
        chart_values=chart_values,
        monthly=monthly
    )


# ================= ADMIN : EXPENSES =================
@app.route("/admin/expenses")
def admin_expenses():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    day = request.args.get("day")
    month = request.args.get("month")
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            c.name AS company,
            CAST(e.amount AS INTEGER) AS amount,
            e.description,
            e.created_at
        FROM expenses e
        JOIN companies c ON e.company_id = c.id
        WHERE 1=1
    """
    params = []

    if day:
        query += " AND date(e.created_at) = ?"
        params.append(day)
    elif month:
        query += " AND strftime('%Y-%m', e.created_at) = ?"
        params.append(month)
    elif date_from and date_to:
        query += " AND date(e.created_at) BETWEEN ? AND ?"
        params.extend([date_from, date_to])

    query += " ORDER BY e.id DESC"

    c.execute(query, params)
    expense_list = c.fetchall()
    conn.close()

    return render_template("admin_expenses.html", expenses=expense_list)


# ================= ADMIN : EXPENSES BY COMPANY =================
@app.route("/admin/expenses/companies")
def admin_expenses_by_company():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            c.id,
            c.name,
            IFNULL(SUM(e.amount),0) AS total_expense
        FROM companies c
        LEFT JOIN expenses e ON e.company_id = c.id
        GROUP BY c.id, c.name
        ORDER BY total_expense DESC
    """)
    companies = c.fetchall()
    conn.close()

    return render_template("admin_expenses_companies.html", companies=companies)


# ================= ADMIN : ASSIGN DIRECTOR =================
@app.route("/admin/assign-director", methods=["POST"])
def assign_director():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    director_id = request.form.get("director_id")
    company_id = request.form.get("company_id")

    if not director_id or not company_id:
        return "Ma'lumotlar yetarli emas ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET company_id=?
        WHERE id=? AND role='director'
    """, (company_id, director_id))

    conn.commit()
    conn.close()

    return redirect(url_for("admin_director_detail", director_id=director_id))


# ================= ADMIN : UNASSIGN DIRECTOR =================
@app.route("/admin/unassign-director/<int:director_id>")
def unassign_director(director_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute(
        "UPDATE users SET company_id=NULL WHERE id=?",
        (director_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_director_detail", director_id=director_id))


# ================= ADMIN : REPORTS =================
@app.route("/admin/reports")
def admin_reports():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    # Kompaniyalar bo'yicha jami xarajat
    c.execute("""
        SELECT c.name, IFNULL(SUM(e.amount),0)
        FROM companies c
        LEFT JOIN expenses e ON e.company_id=c.id
        GROUP BY c.name ORDER BY 2 DESC
    """)
    company_data = c.fetchall()

    # Umumiy statistika
    c.execute("SELECT IFNULL(SUM(balance),0) FROM companies")
    total_balance = c.fetchone()[0]

    c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses")
    total_expenses = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM companies")
    total_companies = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM users WHERE role='director'")
    total_directors = c.fetchone()[0]

    # Oxirgi 12 oylik trend
    c.execute("""
        SELECT strftime('%Y-%m', created_at) as month, IFNULL(SUM(amount),0)
        FROM expenses
        GROUP BY month ORDER BY month DESC LIMIT 12
    """)
    monthly_raw = c.fetchall()
    monthly_data = list(reversed(monthly_raw))

    # Eng ko'p xarajat qilgan top 5 direktor
    c.execute("""
        SELECT u.username, c.name, IFNULL(SUM(e.amount),0) as total
        FROM users u
        LEFT JOIN expenses e ON e.user_id = u.id
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.role='director'
        GROUP BY u.id ORDER BY total DESC LIMIT 5
    """)
    top_directors = c.fetchall()

    # Haftalik xarajat (oxirgi 7 kun)
    weekly_labels = []
    weekly_values = []
    for i in range(6, -1, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses WHERE date(created_at)=?", (day,))
        weekly_labels.append(day[-5:])
        weekly_values.append(c.fetchone()[0])

    conn.close()

    return render_template(
        "admin_reports.html",
        labels=[row[0] for row in company_data],
        values=[row[1] for row in company_data],
        total_balance=total_balance,
        total_expenses=total_expenses,
        total_companies=total_companies,
        total_directors=total_directors,
        monthly_labels=[row[0] for row in monthly_data],
        monthly_values=[row[1] for row in monthly_data],
        top_directors=top_directors,
        weekly_labels=weekly_labels,
        weekly_values=weekly_values,
    )


# ================= ADMIN : BALANCES =================
@app.route("/admin/balances", methods=["GET", "POST"])
def admin_balances():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        company_id = request.form.get("company_id")
        try:
            amount = int(request.form.get("amount", 0))
        except ValueError:
            amount = 0

        if company_id and amount > 0:
            c.execute(
                "UPDATE companies SET balance = balance + ? WHERE id=?",
                (amount, company_id)
            )
            conn.commit()

    c.execute("SELECT id, name, balance FROM companies")
    companies = c.fetchall()
    conn.close()

    return render_template("admin_balances.html", companies=companies)


# ================= ADMIN : COMPANY DIRECTORS =================
@app.route("/admin/company/<int:company_id>/directors")
def admin_company_directors(company_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name FROM companies WHERE id=?", (company_id,))
    company = c.fetchone()
    if not company:
        conn.close()
        return "Kompaniya topilmadi ❌"

    # Tuzatildi: e.user_id = u.id orqali to'g'ri join
    c.execute("""
        SELECT
            u.username,
            IFNULL(SUM(e.amount), 0) AS total
        FROM users u
        LEFT JOIN expenses e ON e.user_id = u.id
        WHERE u.company_id = ? AND u.role='director'
        GROUP BY u.username
    """, (company_id,))
    data = c.fetchall()
    conn.close()

    return render_template(
        "admin_company_directors.html",
        company_name=company["name"],
        data=data
    )


# ================= CLEAR NOTIFICATION =================
@app.route("/clear-notification", methods=["POST"])
def clear_notification():
    session.pop("last_expense", None)
    return redirect(request.referrer or url_for("dashboard"))


# ================= CONTEXT PROCESSOR =================
@app.context_processor
def inject_notifications():
    return {
        "notifications": [],
        "last_expense": session.get("last_expense")
    }





# ================= EXCEL EXPORT =================


def _xl_border():
    s = Side(style="thin", color="E2E8F0")
    return Border(left=s, right=s, top=s, bottom=s)

def _xl_cell(cell, bold=False, color="0F172A", bg=None, align="left",
             size=10, number_fmt=None):
    cell.font = Font(name="Arial", bold=bold, size=size, color=color)
    if bg:
        cell.fill = PatternFill("solid", fgColor=bg)
    cell.alignment = Alignment(horizontal=align, vertical="center")
    if number_fmt:
        cell.number_format = number_fmt
    cell.border = _xl_border()

def _xl_header(ws, title, subtitle, ncols):
    ws.merge_cells(f"A1:{get_column_letter(ncols)}1")
    ws.row_dimensions[1].height = 10
    ws.merge_cells(f"A2:{get_column_letter(ncols)}2")
    c = ws["A2"]
    c.value = title
    c.font = Font(name="Arial", bold=True, size=18, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor="0A0F1E")
    c.alignment = Alignment(horizontal="left", vertical="center", indent=2)
    ws.row_dimensions[2].height = 42
    ws.merge_cells(f"A3:{get_column_letter(ncols)}3")
    c = ws["A3"]
    c.value = subtitle
    c.font = Font(name="Arial", size=10, color="94A3B8")
    c.fill = PatternFill("solid", fgColor="1E3A5F")
    c.alignment = Alignment(horizontal="left", vertical="center", indent=2)
    ws.row_dimensions[3].height = 22
    ws.merge_cells(f"A4:{get_column_letter(ncols)}4")
    ws["A4"].fill = PatternFill("solid", fgColor="0A0F1E")
    ws.row_dimensions[4].height = 6

def _xl_col_headers(ws, row, headers, bg="3B6EF6"):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = Font(name="Arial", bold=True, size=10, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=bg)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = _xl_border()
    ws.row_dimensions[row].height = 26

def _build_xlsx(rows, sheet_title, report_label):
    """rows: list of (company, director, amount, description, created_at)"""
    from collections import defaultdict
    wb = Workbook()

    # ===== SHEET 1: XARAJATLAR =====
    ws = wb.active
    ws.title = sheet_title
    ncols = 5
    _xl_header(ws, f"💸  {report_label.upper()}",
               f"Sana: {datetime.now().strftime('%d.%m.%Y %H:%M')}", ncols)
    widths = [5, 22, 18, 34, 18]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _xl_col_headers(ws, 5, ["#", "Kompaniya", "Summa (so'm)", "Izoh", "Sana"])

    DS = 6
    for idx, row in enumerate(rows, 1):
        r = DS + idx - 1
        bg = "F0F4FF" if idx % 2 == 0 else "FFFFFF"
        for col, val in enumerate([idx, row[0], row[2], row[3], row[4]], 1):
            c = ws.cell(row=r, column=col, value=val)
            _xl_cell(c, bg=bg, align="center" if col == 1 else "left")
            if col == 3:
                _xl_cell(c, bold=True, color="EF4444", bg=bg,
                         align="right", number_fmt="#,##0")
            if col == 5:
                _xl_cell(c, color="64748B", bg=bg)
        ws.row_dimensions[r].height = 20

    DE = DS + len(rows) - 1
    if rows:
        tr = DE + 1
        ws.merge_cells(f"A{tr}:{get_column_letter(2)}{tr}")
        c = ws[f"A{tr}"]
        c.value = "JAMI XARAJAT"
        _xl_cell(c, bold=True, color="FFFFFF", bg="0A0F1E",
                 align="center", size=11)
        tc = ws.cell(row=tr, column=3,
                     value=f"=SUM(C{DS}:C{DE})")
        _xl_cell(tc, bold=True, color="00D4AA", bg="0A0F1E",
                 align="right", size=12, number_fmt="#,##0")
        for col in [4, 5]:
            ws.cell(row=tr, column=col).fill = PatternFill("solid", fgColor="0A0F1E")
            ws.cell(row=tr, column=col).border = _xl_border()
        ws.row_dimensions[tr].height = 28
    ws.freeze_panes = "A6"

    # ===== SHEET 2: KOMPANIYALAR YIG'MA =====
    ws2 = wb.create_sheet("Kompaniyalar")
    company_totals = defaultdict(int)
    for row in rows:
        company_totals[row[0]] += row[2]
    sorted_companies = sorted(company_totals.items(), key=lambda x: -x[1])

    nc2 = 3
    _xl_header(ws2, "🏢  KOMPANIYALAR BO'YICHA YIG'MA",
               f"Sana: {datetime.now().strftime('%d.%m.%Y')}", nc2)
    for i, w in enumerate([5, 26, 20], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    _xl_col_headers(ws2, 5, ["#", "Kompaniya", "Jami xarajat"], bg="00B894")

    DS2 = 6
    for idx, (comp, total) in enumerate(sorted_companies, 1):
        r = DS2 + idx - 1
        bg = "F0FDF4" if idx % 2 == 0 else "FFFFFF"
        for col, val in enumerate([idx, comp, total], 1):
            c = ws2.cell(row=r, column=col, value=val)
            _xl_cell(c, bg=bg, align="center" if col == 1 else "left")
            if col == 3:
                _xl_cell(c, bold=True, color="EF4444", bg=bg,
                         align="right", number_fmt="#,##0")
        ws2.row_dimensions[r].height = 20

    DE2 = DS2 + len(sorted_companies) - 1
    if sorted_companies:
        tr2 = DE2 + 1
        ws2[f"A{tr2}"].value = "JAMI"
        _xl_cell(ws2[f"A{tr2}"], bold=True, color="FFFFFF",
                 bg="0A0F1E", align="center", size=11)
        tc2 = ws2.cell(row=tr2, column=3,
                       value=f"=SUM(C{DS2}:C{DE2})")
        _xl_cell(tc2, bold=True, color="00D4AA", bg="0A0F1E",
                 align="right", size=12, number_fmt="#,##0")
        ws2.cell(row=tr2, column=2).fill = PatternFill("solid", fgColor="0A0F1E")
        ws2.cell(row=tr2, column=2).border = _xl_border()
        ws2.row_dimensions[tr2].height = 28
    ws2.freeze_panes = "A6"

    # ===== SHEET 3: GRAFIK =====
    ws3 = wb.create_sheet("Grafik")
    _xl_header(ws3, "📊  GRAFIK TAHLIL",
               "Kompaniyalar bo'yicha xarajatlar taqqoslash", 4)
    ws3.column_dimensions["A"].width = 24
    ws3.column_dimensions["B"].width = 20
    _xl_col_headers(ws3, 5, ["Kompaniya", "Xarajat (so'm)"])
    for i, (comp, total) in enumerate(sorted_companies, 6):
        ws3.cell(row=i, column=1, value=comp).font = Font(name="Arial", size=10)
        c = ws3.cell(row=i, column=2, value=total)
        c.number_format = "#,##0"
        c.font = Font(name="Arial", size=10, color="EF4444", bold=True)
        ws3.row_dimensions[i].height = 20

    if sorted_companies:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Kompaniyalar bo'yicha xarajatlar"
        chart.y_axis.title = "So'm"
        chart.style = 10
        chart.width = 22
        chart.height = 14
        max_row = 5 + len(sorted_companies)
        data_ref = Reference(ws3, min_col=2, min_row=5, max_row=max_row)
        cats = Reference(ws3, min_col=1, min_row=6, max_row=max_row)
        chart.add_data(data_ref, titles_from_data=True)
        chart.set_categories(cats)
        palette = ["3B6EF6","00D4AA","F59E0B","EF4444","8B5CF6","06B6D4"]
        for i in range(len(sorted_companies)):
            pt = DataPoint(idx=i)
            pt.graphicalProperties.solidFill = palette[i % len(palette)]
            chart.series[0].dPt.append(pt)
        ws3.add_chart(chart, f"A{max_row + 3}")

    return wb


@app.route("/admin/export/expenses")
def export_all_expenses():
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT c.name, u.username, e.amount, e.description, e.created_at
        FROM expenses e
        JOIN companies c ON e.company_id = c.id
        LEFT JOIN users u ON u.id = e.user_id
        ORDER BY e.created_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    wb = _build_xlsx(rows, "Xarajatlar", "Barcha xarajatlar hisoboti")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"xarajatlar_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.route("/admin/export/company/<int:company_id>")
def export_company_expenses(company_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name FROM companies WHERE id=?", (company_id,))
    company = c.fetchone()
    if not company:
        conn.close()
        return "Kompaniya topilmadi ❌"
    c.execute("""
        SELECT c.name, u.username, e.amount, e.description, e.created_at
        FROM expenses e
        JOIN companies c ON e.company_id = c.id
        LEFT JOIN users u ON u.id = e.user_id
        WHERE e.company_id = ?
        ORDER BY e.created_at DESC
    """, (company_id,))
    rows = c.fetchall()
    conn.close()
    wb = _build_xlsx(rows, "Xarajatlar", f"{company['name']} xarajatlari")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"{company['name']}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"})


@app.route("/director/export/expenses")
def export_director_expenses():
    if "user" not in session or session.get("role") != "director":
        return redirect(url_for("login"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, company_id FROM users WHERE username=?", (session["user"],))
    user_row = c.fetchone()
    if not user_row or not user_row["company_id"]:
        conn.close()
        return "Kompaniyaga biriktirilmagansiz ❌"
    c.execute("""
        SELECT c.name, u.username, e.amount, e.description, e.created_at
        FROM expenses e
        JOIN companies c ON e.company_id = c.id
        JOIN users u ON u.id = e.user_id
        WHERE e.company_id = ? AND e.user_id = ?
        ORDER BY e.created_at DESC
    """, (user_row["company_id"], user_row["id"]))
    rows = c.fetchall()
    conn.close()
    wb = _build_xlsx(rows, "Xarajatlarim", f"{session['user']} xarajatlari")
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"{session['user']}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return Response(buf.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"})


# ================= ISHCHILAR =================
@app.route("/workers", methods=["GET", "POST"])
def workers():
    if "user" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "director":
        return "Ruxsat yo'q ❌"

    conn = get_db()
    c = conn.cursor()

    # Direktorning kompaniyasini topamiz
    c.execute("SELECT company_id FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    company_id = row["company_id"] if row else None

    error = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            full_name = request.form.get("full_name", "").strip()
            position = request.form.get("position", "").strip()
            phone = request.form.get("phone", "").strip()
            monthly_salary = int(request.form.get("monthly_salary", 0) or 0)
            if full_name:
                c.execute(
                    "INSERT INTO workers (full_name, position, phone, company_id, monthly_salary, created_at) VALUES (?,?,?,?,?,?)",
                    (full_name, position, phone, company_id, monthly_salary, datetime.now().strftime("%Y-%m-%d %H:%M"))
                )
                conn.commit()

        elif action == "salary":
            worker_id = int(request.form.get("worker_id", 0))
            amount = int(request.form.get("amount", 0))
            note = request.form.get("note", "").strip()

            # Balansni tekshirish
            c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
            bal = c.fetchone()
            if not bal or bal["balance"] < amount:
                error = "Balans yetarli emas!"
            elif amount <= 0:
                error = "Summa 0 dan katta bo'lishi kerak!"
            else:
                c.execute(
                    "INSERT INTO salaries (worker_id, company_id, amount, note, created_at) VALUES (?,?,?,?,?)",
                    (worker_id, company_id, amount, note, datetime.now().strftime("%Y-%m-%d %H:%M"))
                )
                c.execute("UPDATE companies SET balance = balance - ? WHERE id=?", (amount, company_id))
                conn.commit()

        elif action == "delete":
            worker_id = int(request.form.get("worker_id", 0))
            c.execute("DELETE FROM workers WHERE id=? AND company_id=?", (worker_id, company_id))
            c.execute("DELETE FROM salaries WHERE worker_id=?", (worker_id,))
            conn.commit()

        conn.close()
        return redirect(url_for("workers"))

    # Ishchilar ro'yxati
    c.execute("""
        SELECT w.id, w.full_name, w.position, w.phone, w.created_at,
               IFNULL(SUM(s.amount), 0) AS total_salary
        FROM workers w
        LEFT JOIN salaries s ON s.worker_id = w.id
        WHERE w.company_id=?
        GROUP BY w.id
        ORDER BY w.id DESC
    """, (company_id,))
    worker_list = c.fetchall()

    # Kompaniya balansi
    c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
    bal_row = c.fetchone()
    balance = bal_row["balance"] if bal_row else 0

    conn.close()
    return render_template("workers.html", workers=worker_list, balance=balance, error=error)


@app.route('/ping')
def ping():
    return 'pong', 200


# ================= WORKER DETAIL =================
@app.route("/workers/<int:worker_id>", methods=["GET", "POST"])
def worker_detail(worker_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    c = conn.cursor()

    # company_id ni DB dan olamiz — session da bo'lmasa ham ishlaydi
    c.execute("SELECT company_id FROM users WHERE id=?", (session["user_id"],))
    u = c.fetchone()
    company_id = u["company_id"] if u else session.get("company_id")

    c.execute("SELECT * FROM workers WHERE id=? AND company_id=?", (worker_id, company_id))
    worker = c.fetchone()
    if not worker:
        conn.close()
        return "Ishchi topilmadi", 404

    error = ""
    success = ""

    if request.method == "POST":
        action = request.form.get("action")

        if action == "toggle_status":
            new_status = "paused" if worker["status"] == "active" else "active"
            c.execute("UPDATE workers SET status=? WHERE id=?", (new_status, worker_id))
            conn.commit()

        elif action == "update_salary":
            new_salary = int(request.form.get("monthly_salary", 0) or 0)
            c.execute("UPDATE workers SET monthly_salary=? WHERE id=?", (new_salary, worker_id))
            conn.commit()
            success = "Oylik maosh yangilandi!"

        elif action == "attendance":
            date = request.form.get("date")
            att_status = request.form.get("att_status", "absent")
            note = request.form.get("note", "")
            c.execute("SELECT id FROM attendance WHERE worker_id=? AND date=?", (worker_id, date))
            if c.fetchone():
                c.execute("UPDATE attendance SET status=?, note=? WHERE worker_id=? AND date=?",
                          (att_status, note, worker_id, date))
            else:
                c.execute("INSERT INTO attendance (worker_id, company_id, date, status, note, created_at) VALUES (?,?,?,?,?,?)",
                          (worker_id, company_id, date, att_status, note, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()

        elif action == "advance":
            amount = int(request.form.get("amount", 0) or 0)
            note = request.form.get("note", "").strip()
            c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
            bal = c.fetchone()
            if not bal or bal["balance"] < amount:
                error = "Balans yetarli emas!"
            elif amount <= 0:
                error = "Summa 0 dan katta bo'lishi kerak!"
            else:
                c.execute("INSERT INTO advances (worker_id, company_id, amount, note, created_at) VALUES (?,?,?,?,?)",
                          (worker_id, company_id, amount, note, datetime.now().strftime("%Y-%m-%d %H:%M")))
                c.execute("UPDATE companies SET balance = balance - ? WHERE id=?", (amount, company_id))
                conn.commit()
                success = "Avans berildi!"

        elif action == "pay_salary":
            amount = int(request.form.get("amount", 0) or 0)
            note = request.form.get("note", "").strip()
            c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
            bal = c.fetchone()
            if not bal or bal["balance"] < amount:
                error = "Balans yetarli emas!"
            elif amount <= 0:
                error = "Summa 0 dan katta bo'lishi kerak!"
            else:
                c.execute("INSERT INTO salaries (worker_id, company_id, amount, note, created_at) VALUES (?,?,?,?,?)",
                          (worker_id, company_id, amount, note, datetime.now().strftime("%Y-%m-%d %H:%M")))
                c.execute("UPDATE companies SET balance = balance - ? WHERE id=?", (amount, company_id))
                conn.commit()
                success = "Maosh to'landi!"

        conn.close()
        return redirect(url_for("worker_detail", worker_id=worker_id))

    now = datetime.now()
    month_str = now.strftime("%Y-%m")

    c.execute("SELECT IFNULL(SUM(amount),0) FROM salaries WHERE worker_id=? AND created_at LIKE ?",
              (worker_id, month_str + "%"))
    month_salary_paid = c.fetchone()[0]

    c.execute("SELECT IFNULL(SUM(amount),0) FROM advances WHERE worker_id=? AND created_at LIKE ?",
              (worker_id, month_str + "%"))
    month_advances = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM attendance WHERE worker_id=? AND status='present' AND date LIKE ?",
              (worker_id, month_str + "%"))
    days_present = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM attendance WHERE worker_id=? AND status='absent' AND date LIKE ?",
              (worker_id, month_str + "%"))
    days_absent = c.fetchone()[0]

    monthly_salary = worker["monthly_salary"] or 0
    salary_left = monthly_salary - month_salary_paid - month_advances

    c.execute("SELECT date, status, note FROM attendance WHERE worker_id=? ORDER BY date DESC LIMIT 30",
              (worker_id,))
    attendance_list = c.fetchall()

    c.execute("SELECT amount, note, created_at FROM salaries WHERE worker_id=? ORDER BY created_at DESC LIMIT 10",
              (worker_id,))
    salary_history = c.fetchall()

    c.execute("SELECT amount, note, created_at FROM advances WHERE worker_id=? ORDER BY created_at DESC LIMIT 10",
              (worker_id,))
    advance_history = c.fetchall()

    c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
    bal_row = c.fetchone()
    balance = bal_row["balance"] if bal_row else 0

    conn.close()
    return render_template("worker_detail.html",
        worker=worker,
        month_salary_paid=month_salary_paid,
        month_advances=month_advances,
        days_present=days_present,
        days_absent=days_absent,
        salary_left=salary_left,
        attendance_list=attendance_list,
        salary_history=salary_history,
        advance_history=advance_history,
        balance=balance,
        error=error,
        success=success,
        today=now.strftime("%Y-%m-%d"),
        month_name=now.strftime("%B %Y")
    )


@app.route("/admin/delete-company/<int:company_id>", methods=["POST"])
def delete_company(company_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"
    conn = get_db()
    c = conn.cursor()
    # Kompaniyaga bog'liq direktorlarni ajratib olamiz
    c.execute("UPDATE users SET company_id=NULL WHERE company_id=?", (company_id,))
    # Kompaniya xarajatlarini o'chiramiz
    c.execute("DELETE FROM expenses WHERE company_id=?", (company_id,))
    # Kompaniyani o'chiramiz
    c.execute("DELETE FROM companies WHERE id=?", (company_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_companies"))


@app.route("/admin/delete-director/<int:director_id>", methods=["POST"])
def delete_director(director_id):
    if session.get("role") != "admin":
        return "Ruxsat yo'q ❌"
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=? AND role='director'", (director_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_directors"))

# ================= QOLDI MODAL API =================
@app.route('/api/company-balances')
def company_balances():
    if 'user' not in session:
        return {'error': 'login required'}, 401
    from flask import jsonify
    conn = get_db()
    c = conn.cursor()
    if session.get('role') == 'admin':
        c.execute("SELECT name, balance FROM companies ORDER BY balance DESC")
    else:
        c.execute("SELECT name, balance FROM companies WHERE id=?", (session.get('company_id'),))
    rows = [{'name': r['name'], 'balance': r['balance']} for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

# ================= RUN =================
init_db()  # Gunicorn va oddiy run ikkalasida ham ishlaydi

if __name__ == "__main__":
    app.run(debug=False)