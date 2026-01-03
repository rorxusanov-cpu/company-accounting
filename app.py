from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime, timedelta


app = Flask(__name__)
app.secret_key = "VERY_SECRET_KEY_123456"



# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    
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

    c.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        amount INTEGER,
        description TEXT,
        created_at TEXT
    )
    """)

    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchone():
        c.execute("""
            INSERT INTO users (username, password, role, created_at)
            VALUES ('admin', 'admin', 'admin', ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M"),))

    conn.commit()
    conn.close()

    


# ================= AUTH =================
@app.route("/", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute(
            "SELECT username, role FROM users WHERE username=? AND password=?",
            (username, password)
        )
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = user[0]
            session["role"] = user[1]
            
            return redirect(url_for("dashboard"))
        else:
            error = "Login yoki parol noto‘g‘ri!"

    return render_template("login.html", error=error)



@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = ""
    if request.method == "POST":
        try:
            conn = sqlite3.connect("users.db")
            c = conn.cursor()
            c.execute("""
                INSERT INTO users (username, password, role, created_at)
                VALUES (?, ?, 'director', ?)
            """, (
                request.form["username"],
                request.form["password"],
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except:
            error = "Bu login mavjud!"

    return render_template("signup.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))




    # ================= ADMIN DASHBOARD =================
 # ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    role = session.get("role")
    username = session.get("user")

    # ===== FILTERLAR =====
    period = request.args.get("period")        # day | month | year
    date_from = request.args.get("from")       # YYYY-MM-DD
    date_to = request.args.get("to")           # YYYY-MM-DD

    # ===== DEFAULT =====
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


        # ===== FILTER LOGIC (ADMIN) =====
        if period == "day":
            c.execute("""
                SELECT strftime('%H', created_at), SUM(amount)
                FROM expenses
                WHERE date(created_at)=date('now')
                GROUP BY strftime('%H', created_at)
            """)
            data = c.fetchall()
            labels = [f"{h}:00" for h, _ in data]
            values = [v for _, v in data]

        elif period == "month":
            c.execute("""
                SELECT date(created_at), SUM(amount)
                FROM expenses
                WHERE strftime('%Y-%m', created_at)=strftime('%Y-%m','now')
                GROUP BY date(created_at)
            """)
            data = c.fetchall()
            labels = [d for d, _ in data]
            values = [v for _, v in data]

        elif period == "year":
            c.execute("""
                SELECT strftime('%Y-%m', created_at), SUM(amount)
                FROM expenses
                WHERE strftime('%Y', created_at)=strftime('%Y','now')
                GROUP BY strftime('%Y-%m', created_at)
            """)
            data = c.fetchall()
            labels = [d for d, _ in data]
            values = [v for _, v in data]

        elif date_from and date_to:
            c.execute("""
                SELECT date(created_at), SUM(amount)
                FROM expenses
                WHERE date(created_at) BETWEEN ? AND ?
                GROUP BY date(created_at)
            """, (date_from, date_to))
            data = c.fetchall()
            labels = [d for d, _ in data]
            values = [v for _, v in data]

        else:
            # DEFAULT: oxirgi 7 kun
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

        if not row or not row[0]:
            warning = "Siz kompaniyaga biriktirilmagansiz"
        else:
            company_id = row[0]

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

            # ===== FILTER LOGIC (DIRECTOR) =====
            if period == "day":
                c.execute("""
                    SELECT strftime('%H', created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND date(created_at)=date('now')
                    GROUP BY strftime('%H', created_at)
                """, (company_id,))
                data = c.fetchall()
                labels = [f"{h}:00" for h, _ in data]
                values = [v for _, v in data]

            elif period == "month":
                c.execute("""
                    SELECT date(created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND strftime('%Y-%m', created_at)=strftime('%Y-%m','now')
                    GROUP BY date(created_at)
                """, (company_id,))
                data = c.fetchall()
                labels = [d for d, _ in data]
                values = [v for _, v in data]

            elif period == "year":
                c.execute("""
                    SELECT strftime('%Y-%m', created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND strftime('%Y', created_at)=strftime('%Y','now')
                    GROUP BY strftime('%Y-%m', created_at)
                """, (company_id,))
                data = c.fetchall()
                labels = [d for d, _ in data]
                values = [v for _, v in data]

            elif date_from and date_to:
                c.execute("""
                    SELECT date(created_at), SUM(amount)
                    FROM expenses
                    WHERE company_id=? AND date(created_at) BETWEEN ? AND ?
                    GROUP BY date(created_at)
                """, (company_id, date_from, date_to))
                data = c.fetchall()
                labels = [d for d, _ in data]
                values = [v for _, v in data]

            else:
                # DEFAULT: oxirgi 7 kun
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
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row   # ⭐ MUHIM
    c = conn.cursor()

    # ================= ADD COMPANY =================
    if request.method == "POST":
        name = request.form["name"]
        balance = int(request.form["balance"])

        c.execute(
            "INSERT INTO companies (name, balance) VALUES (?, ?)",
            (name, balance)
        )
        conn.commit()

        return redirect(url_for("admin_companies"))

    # ================= GET COMPANIES =================
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

    return render_template(
        "admin_companies.html",
        companies=companies
    )


# ================= EXPENSES (DIRECTOR) =================
@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    # 🔐 Login tekshiruvi
    if "user" not in session:
        return redirect(url_for("login"))

    # 🔐 Faqat director kiradi
    if session.get("role") != "director":
        return redirect(url_for("dashboard"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # 🏢 Director kompaniyasini olish
    c.execute(
        "SELECT company_id FROM users WHERE username=?",
        (session["user"],)
    )
    row = c.fetchone()

    # ❌ Agar kompaniya yo‘q bo‘lsa
    if not row or row[0] is None:
        conn.close()
        return render_template(
            "expenses.html",
            expenses=[],
            balance=0,
            error="Siz kompaniyaga biriktirilmagansiz ❌"
        )

    company_id = row[0]

    # ================= POST: XARAJAT QO‘SHISH =================
    if request.method == "POST":
        amount = int(request.form["amount"])
        description = request.form["description"]

        # 💰 Balansni olish
        c.execute(
            "SELECT balance FROM companies WHERE id=?",
            (company_id,)
        )
        balance = c.fetchone()[0]

        # ❌ Manfiy yoki 0 summa
        if amount <= 0:
            conn.close()
            return render_template(
                "expenses.html",
                expenses=[],
                balance=balance,
                error="Xarajat summasi noto‘g‘ri ❌"
            )

        # ❌ Balans yetarli emas
        if amount > balance:
            conn.close()
            return render_template(
                "expenses.html",
                expenses=[],
                balance=balance,
                error="Balans yetarli emas ❌"
            )

        # ✅ Xarajat qo‘shish
        c.execute("""
            INSERT INTO expenses (company_id, amount, description, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            company_id,
            amount,
            description,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

        # ➖ Balansni kamaytirish
        c.execute(
            "UPDATE companies SET balance = balance - ? WHERE id=?",
            (amount, company_id)
        )

        conn.commit()

        # 🔔 ===== NOTIFICATION (ASOSIY QO‘SHILGAN JOY) =====
        session["last_expense"] = {
            "message": f"💸 {amount} so‘m xarajat qo‘shildi",
            "time": datetime.now().strftime("%H:%M")
        }

        # 🔁 POST → REDIRECT (refresh muammosi bo‘lmasin)
        conn.close()
        return redirect(url_for("expenses"))

    # ================= XARAJATLARNI KO‘RISH =================
    c.execute("""
        SELECT amount, description, created_at
        FROM expenses
        WHERE company_id=?
        ORDER BY id DESC
    """, (company_id,))
    expenses = c.fetchall()

    # 💰 Balansni qayta olish
    c.execute(
        "SELECT balance FROM companies WHERE id=?",
        (company_id,)
    )
    balance = c.fetchone()[0]

    conn.close()

    return render_template(
        "expenses.html",
        expenses=expenses,
        balance=balance,
        error=None
    )



# ================= ADMIN : DIRECTOR DETAIL =================
@app.route("/admin/director/<int:director_id>", methods=["GET", "POST"])
def admin_director_detail(director_id):
    # 🔐 Faqat admin
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ================= DIRECTOR =================
    c.execute("""
        SELECT 
            u.id,
            u.username,
            u.created_at,
            c.name AS company
        FROM users u
        LEFT JOIN companies c ON u.company_id = c.id
        WHERE u.id = ?
    """, (director_id,))
    director = c.fetchone()

    if not director:
        conn.close()
        return "Direktor topilmadi ❌"

    # ================= POST → BIRIKTIRISH =================
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

    # ================= KOMPANIYALAR RO‘YXATI =================
    c.execute("SELECT id, name FROM companies")
    companies = c.fetchall()

    # ================= BALANS =================
    if director["company"]:
        c.execute("""
            SELECT balance 
            FROM companies 
            WHERE name=?
        """, (director["company"],))
        company_balance = c.fetchone()["balance"]

        c.execute("""
            SELECT IFNULL(SUM(amount), 0)
            FROM expenses
            WHERE company_id = (
                SELECT id FROM companies WHERE name=?
            )
        """, (director["company"],))
        total_expenses = c.fetchone()[0]
    else:
        company_balance = 0
        total_expenses = 0

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
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row   # 🔥 MUHIM
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

    return render_template(
        "admin_directors.html",
        directors=directors
    )



@app.route("/admin/company/<int:company_id>")
def admin_company_detail(company_id):
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # COMPANY
    c.execute(
        "SELECT id, name, balance, created_at FROM companies WHERE id=?",
        (company_id,)
    )
    company = c.fetchone()
    if not company:
        conn.close()
        return "Kompaniya topilmadi ❌"

    # TOTAL EXPENSES
    c.execute(
        "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=?",
        (company_id,)
    )
    total_expenses = c.fetchone()[0]

    # DIRECTORS + THEIR EXPENSES
    c.execute("""
        SELECT 
            u.id,
            u.username,
            IFNULL(SUM(e.amount),0) AS total
        FROM users u
        LEFT JOIN expenses e 
            ON e.company_id = u.company_id
        WHERE u.company_id=? AND u.role='director'
        GROUP BY u.id
    """, (company_id,))
    directors = c.fetchall()

    # FILTER
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
        LEFT JOIN users u 
            ON u.company_id = e.company_id AND u.role='director'
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
    expenses = c.fetchall()

    conn.close()

    return render_template(
        "admin_company_detail.html",
        company=company,
        total_expenses=total_expenses,
        directors=directors,
        expenses=expenses
    )


# ================= ADMIN : EXPENSES =================
@app.route("/admin/expenses")
def admin_expenses():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    # filter parametrlari
    day   = request.args.get("day")
    month = request.args.get("month")
    date_from = request.args.get("from")
    date_to   = request.args.get("to")

    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
        SELECT 
            c.name        AS company,
            CAST(e.amount AS INTEGER) AS amount,
            e.description,
            e.created_at
        FROM expenses e
        JOIN companies c ON e.company_id = c.id
        WHERE 1=1
    """
    params = []

    # 📅 KUNLIK
    if day:
        query += " AND date(e.created_at) = ?"
        params.append(day)

    # 📆 OYLIK
    elif month:
        query += " AND strftime('%Y-%m', e.created_at) = ?"
        params.append(month)

    # 🗓 FROM – TO
    elif date_from and date_to:
        query += " AND date(e.created_at) BETWEEN ? AND ?"
        params.extend([date_from, date_to])

    query += " ORDER BY e.id DESC"

    c.execute(query, params)
    expenses = c.fetchall()
    conn.close()

    return render_template(
        "admin_expenses.html",
        expenses=expenses
    )

@app.context_processor
def inject_notifications():
    return {
        "notifications": [],
        "last_expense": session.get("last_expense")
    }





@app.route("/admin/expenses/companies")
def admin_expenses_by_company():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
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

    return render_template(
        "admin_expenses_companies.html",
        companies=companies
    )

@app.route("/admin/assign-director", methods=["POST"])
def assign_director():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    director_id = request.form["director_id"]
    company_id = request.form["company_id"]

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        UPDATE users 
        SET company_id=? 
        WHERE id=? AND role='director'
    """, (company_id, director_id))

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin_director_detail", director_id=director_id)
    )

@app.route("/admin/unassign-director/<int:director_id>")
def unassign_director(director_id):
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
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
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
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
        labels=[d[0] for d in data],
        values=[d[1] for d in data]
    )


# ================= ADMIN : BALANCES =================
@app.route("/admin/balances", methods=["GET", "POST"])
def admin_balances():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # 🔁 BALANS TO‘LDIRISH
    if request.method == "POST":
        company_id = request.form["company_id"]
        amount = int(request.form["amount"])

        c.execute(
            "UPDATE companies SET balance = balance + ? WHERE id=?",
            (amount, company_id)
        )
        conn.commit()

    # 📋 RO‘YXAT
    c.execute("SELECT id, name, balance FROM companies")
    companies = c.fetchall()
    conn.close()

    return render_template("admin_balances.html", companies=companies)
@app.route("/admin/company/<int:company_id>/directors")
def admin_company_directors(company_id):
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # Kompaniya nomi
    c.execute("SELECT name FROM companies WHERE id=?", (company_id,))
    company = c.fetchone()
    if not company:
        conn.close()
        return "Kompaniya topilmadi ❌"

    # Direktorlar bo‘yicha xarajatlar
    c.execute("""
        SELECT 
            u.username,
            IFNULL(SUM(e.amount), 0)
        FROM users u
        LEFT JOIN expenses e ON e.company_id = u.company_id
        WHERE u.company_id = ? AND u.role='director'
        GROUP BY u.username
    """, (company_id,))

    data = c.fetchall()
    conn.close()

    return render_template(
        "admin_company_directors.html",
        company_name=company[0],
        data=data
    )
@app.route("/clear-notification", methods=["POST"])
def clear_notification():
    session.pop("last_expense", None)
    return redirect(request.referrer or url_for("dashboard"))



# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
