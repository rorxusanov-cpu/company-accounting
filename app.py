from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime
import os


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")



# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # USERS
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

    # COMPANIES
    c.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            balance INTEGER,
            created_at TEXT
        )
    """)

    # EXPENSES
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

    conn.commit()
    conn.close()



# ================= LOGIN =================
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


# ================= SIGNUP =================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = ""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = "user"  # director
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            conn = sqlite3.connect("users.db")
            c = conn.cursor()
            c.execute(
                "INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                (username, password, role, created_at)
            )
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except:
            error = "Bu login allaqachon mavjud!"

    return render_template("signup.html", error=error)


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html")


# ================= PROFILE =================
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute(
        "SELECT id, username, role, created_at FROM users WHERE username=?",
        (session["user"],)
    )
    user = c.fetchone()
    conn.close()

    return render_template(
        "profile.html",
        user_id=user[0],
        username=user[1],
        role=user[2],
        created_at=user[3]
    )


# ================= ABOUT =================
@app.route("/about")
def about():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("about.html")


# ================= ADMIN : DIRECTORS =================
@app.route("/admin/directors")
def admin_directors():
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        SELECT id, username, role, created_at
        FROM users
        WHERE role = 'user'
    """)
    directors = c.fetchall()
    conn.close()

    return render_template("admin_directors.html", directors=directors)


# ================= ADMIN : COMPANIES =================
@app.route("/admin/companies", methods=["GET", "POST"])
def admin_companies():
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        balance = request.form["balance"]
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            c.execute(
                "INSERT INTO companies (name, balance, created_at) VALUES (?, ?, ?)",
                (name, balance, created_at)
            )
            conn.commit()
        except:
            pass

    c.execute("SELECT id, name, balance, created_at FROM companies")
    companies = c.fetchall()
    conn.close()

    return render_template("admin_companies.html", companies=companies)


# ================= DIREKTORNI BOG‘LASH =================
@app.route("/admin/assign-director", methods=["GET", "POST"])
def assign_director():
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        director_id = request.form["director_id"]
        company_id = request.form["company_id"]

        c.execute(
            "UPDATE users SET company_id=? WHERE id=?",
            (company_id, director_id)
        )
        conn.commit()

    # directorlar
    c.execute("SELECT id, username FROM users WHERE role='user'")
    directors = c.fetchall()

    # kompaniyalar
    c.execute("SELECT id, name FROM companies")
    companies = c.fetchall()

    conn.close()

    return render_template(
        "admin_assign_director.html",
        directors=directors,
        companies=companies
    )
# ================= XARAJAT KIRITADI =================
@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # direktor kompaniyasi
    c.execute("SELECT company_id FROM users WHERE username=?", (session["user"],))
    company_id = c.fetchone()[0]

    if company_id is None:
        return "Siz kompaniyaga biriktirilmagansiz ❌"

    if request.method == "POST":
        amount = int(request.form["amount"])
        description = request.form["description"]
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        # xarajat qo‘shish
        c.execute(
            "INSERT INTO expenses (company_id, amount, description, created_at) VALUES (?, ?, ?, ?)",
            (company_id, amount, description, created_at)
        )

        # balansni kamaytirish
        c.execute(
            "UPDATE companies SET balance = balance - ? WHERE id=?",
            (amount, company_id)
        )

        conn.commit()

    # xarajatlar
    c.execute("""
        SELECT amount, description, created_at
        FROM expenses
        WHERE company_id=?
        ORDER BY id DESC
    """, (company_id,))
    expenses = c.fetchall()

    # balans
    c.execute("SELECT balance FROM companies WHERE id=?", (company_id,))
    balance = c.fetchone()[0]

    conn.close()

    return render_template("expenses.html", expenses=expenses, balance=balance)

# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
# ================= HAMMA XARAJATLARNI KO‘RADI =================

@app.route("/admin/expenses")
def admin_expenses():
    if "user" not in session or session.get("role") != "admin":
        return "Ruxsat yo‘q ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        SELECT companies.name, expenses.amount, expenses.description, expenses.created_at
        FROM expenses
        JOIN companies ON expenses.company_id = companies.id
        ORDER BY expenses.id DESC
    """)

    expenses = c.fetchall()
    conn.close()

    return render_template("admin_expenses.html", expenses=expenses)
# ================= DIREKTOR UCHUN XARAJAT QO‘SHISH SAHIFASI =================
@app.route("/expenses", methods=["GET", "POST"])
def expenses():
    if "user" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "director":
        return "Faqat direktorlar uchun ❌"

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    # user id
    c.execute("SELECT id FROM users WHERE username=?", (session["user"],))
    user_id = c.fetchone()[0]

    if request.method == "POST":
        amount = request.form["amount"]
        description = request.form["description"]
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

        # vaqtincha company_id = 1
        c.execute("""
            INSERT INTO expenses (company_id, user_id, amount, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (1, user_id, amount, description, created_at))

        # balansdan ayiramiz
        c.execute("UPDATE companies SET balance = balance - ? WHERE id = 1", (amount,))
        conn.commit()

    c.execute("""
        SELECT amount, description, created_at
        FROM expenses
        WHERE user_id=?
        ORDER BY created_at DESC
    """, (user_id,))
    expenses = c.fetchall()

    conn.close()
    return render_template("expenses.html", expenses=expenses)

# ================= RUN =================
if __name__ == "__main__":
    init_db()
    app.run()
