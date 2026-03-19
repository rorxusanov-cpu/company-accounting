from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta
import requests
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ================= CONFIG =================
# .env faylidan o'qiladi, aks holda default qiymat
app.secret_key = os.environ.get("SECRET_KEY", "o'zgartiring-bu-qiymatni")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8588085417:AAG1_uFr9irp7-E2fGd20jg0BbxxUopSsH4")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5703562662")


# ================= TELEGRAM =================
def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print("Telegram xato:", e)


# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect("users.db")
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
            "SELECT id, username, password, role FROM users WHERE username=?",
            (username,)
        )
        user = c.fetchone()
        conn.close()

        # check_password_hash — parolni xavfsiz tekshiradi
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user"] = user["username"]
            session["role"] = user["role"]
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

    if director["company_id_val"]:
        c.execute(
            "SELECT balance FROM companies WHERE id=?",
            (director["company_id_val"],)
        )
        row = c.fetchone()
        if row:
            company_balance = row["balance"]

        c.execute(
            "SELECT IFNULL(SUM(amount), 0) FROM expenses WHERE company_id=?",
            (director["company_id_val"],)
        )
        total_expenses = c.fetchone()[0]

    conn.close()

    return render_template(
        "admin_director_detail.html",
        director=director,
        companies=companies,
        company_balance=company_balance,
        total_expenses=total_expenses
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

    conn.close()

    return render_template(
        "admin_company_detail.html",
        company=company,
        total_expenses=total_expenses,
        directors=directors,
        expenses=expense_list
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

    c.execute("""
        SELECT c.name, IFNULL(SUM(e.amount),0)
        FROM companies c
        LEFT JOIN expenses e ON e.company_id=c.id
        GROUP BY c.name
    """)
    data = c.fetchall()
    conn.close()

    return render_template(
        "admin_reports.html",
        labels=[row[0] for row in data],
        values=[row[1] for row in data]
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


# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run(debug=False)