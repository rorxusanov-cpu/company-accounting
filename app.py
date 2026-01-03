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


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    role = session.get("role")
    username = session.get("user")

    # ================= ADMIN DASHBOARD =================
    if role == "admin":
        c.execute("SELECT IFNULL(SUM(balance),0) FROM companies")
        total_balance = c.fetchone()[0]

        c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses")
        total_expenses = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM companies")
        companies_count = c.fetchone()[0]

        profit = total_balance - total_expenses

        labels, values = [], []
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            c.execute(
                "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE date(created_at)=?",
                (day,)
            )
            labels.append(day)
            values.append(c.fetchone()[0])

    # ================= DIRECTOR DASHBOARD =================
    else:
        # direktor kompaniyasi
        c.execute("SELECT company_id FROM users WHERE username=?", (username,))
        row = c.fetchone()

        if not row or not row[0]:
            conn.close()
            return render_template(
                "dashboard.html",
                warning="Siz kompaniyaga biriktirilmagansiz",
                total_balance=0,
                total_expenses=0,
                profit=0,
                companies_count=0,
                labels=[],
                values=[]
            )

        company_id = row[0]

        c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
        total_balance = c.fetchone()[0]

        c.execute(
            "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=?",
            (company_id,)
        )
        total_expenses = c.fetchone()[0]

        profit = total_balance - total_expenses
        companies_count = 1

        labels, values = [], []
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
        warning=None
    )

# ================= ADMIN : COMPANIES =================
@app.route("/admin/companies", methods=["GET", "POST"])
def admin_companies():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        c.execute(
            "INSERT INTO companies (name, balance, created_at) VALUES (?, ?, ?)",
            (
                request.form["name"],
                int(request.form["balance"]),
                datetime.now().strftime("%Y-%m-%d %H:%M")
            )
        )
        conn.commit()

    c.execute("""
        SELECT c.id, c.name, c.balance, IFNULL(u.username,'—'), c.created_at
        FROM companies c
        LEFT JOIN users u ON u.company_id = c.id
    """)
    companies = c.fetchall()
    conn.close()

    return render_template("admin_companies.html", companies=companies)
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



@app.route("/admin/company/<int:company_id>")
def admin_company_detail(company_id):
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # kompaniya
    c.execute(
        "SELECT name, balance, created_at FROM companies WHERE id=?",
        (company_id,)
    )
    company = c.fetchone()

    if not company:
        conn.close()
        return "Kompaniya topilmadi ❌"

    name, balance, created_at = company

    # direktorlar
    c.execute("""
        SELECT username
        FROM users
        WHERE role='director' AND company_id=?
    """, (company_id,))
    directors = c.fetchall()

    # xarajatlar
    c.execute("""
        SELECT amount, description, created_at
        FROM expenses
        WHERE company_id=?
        ORDER BY id DESC
    """, (company_id,))
    expenses = c.fetchall()

    conn.close()

    return render_template(
        "admin_company_detail.html",
        company_id=company_id,
        name=name,
        balance=balance,
        created_at=created_at,
        directors=directors,
        expenses=expenses
    )


# ================= ADMIN : DIRECTOR DETAIL =================
@app.route("/admin/director/<int:director_id>")
def admin_director_detail(director_id):
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        SELECT u.username, u.created_at, u.company_id,
               IFNULL(cmp.name, 'Biriktirilmagan')
        FROM users u
        LEFT JOIN companies cmp ON u.company_id = cmp.id
        WHERE u.id = ?
    """, (director_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return "Direktor topilmadi ❌"

    username, created_at, company_id, company_name = row

    balance = 0
    total_expenses = 0

    if company_id:
        c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
        balance = c.fetchone()[0]

        c.execute(
            "SELECT IFNULL(SUM(amount),0) FROM expenses WHERE company_id=?",
            (company_id,)
        )
        total_expenses = c.fetchone()[0]

    c.execute("SELECT id, name FROM companies")
    companies = c.fetchall()

    conn.close()

    return render_template(
        "admin_director_detail.html",
        director_id=director_id,
        username=username,
        created_at=created_at,
        company_id=company_id,
        company_name=company_name,
        balance=balance,
        total_expenses=total_expenses,
        companies=companies
    )

# ================= ADMIN : DIRECTORS =================
@app.route("/admin/directors")
def admin_directors():
    if "user" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        SELECT 
            u.id,
            u.username,
            IFNULL(c.name, 'Biriktirilmagan'),
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


# ================= ADMIN : EXPENSES =================
@app.route("/admin/expenses")
def admin_expenses():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        SELECT c.name, e.amount, e.description, e.created_at
        FROM expenses e
        JOIN companies c ON e.company_id=c.id
        ORDER BY e.id DESC
    """)
    expenses = c.fetchall()
    conn.close()
    return render_template("admin_expenses.html", expenses=expenses)


@app.route("/admin/expenses/companies")
def admin_expenses_by_company():
    if session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        SELECT c.id, c.name, IFNULL(SUM(e.amount),0)
        FROM companies c
        LEFT JOIN expenses e ON e.company_id=c.id
        GROUP BY c.id
    """)
    companies = c.fetchall()
    conn.close()
    return render_template("admin_expenses_companies.html", companies=companies)
@app.route("/admin/assign-director", methods=["POST"])
def assign_director():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    director_id = request.form["director_id"]
    company_id = request.form["company_id"]

    c.execute(
        "UPDATE users SET company_id=? WHERE id=? AND role='director'",
        (company_id, director_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_director_detail", director_id=director_id))
@app.route("/admin/unassign-director/<int:director_id>")
def unassign_director(director_id):
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute(
        "UPDATE users SET company_id = NULL WHERE id=? AND role='director'",
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

# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
