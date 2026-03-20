import sqlite3, os, io, requests
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side,
                              GradientFill)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, Reference
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                 Paragraph, Spacer, HRFlowable, PageBreak)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8588085417:AAG1_uFr9irp7-E2fGd20jg0BbxxUopSsH4")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "5703562662")
DB_PATH = "/data/users.db" if os.path.exists("/data") else "users.db"
TODAY = datetime.now().strftime("%Y-%m-%d")
NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
MONTH = datetime.now().strftime("%Y-%m")
MONTH_NAME = datetime.now().strftime("%B %Y")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_report_data():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT c.id, c.name, c.balance,
               IFNULL((SELECT SUM(amount) FROM expenses WHERE company_id=c.id AND date(created_at)=date('now')), 0) as today_exp,
               IFNULL((SELECT SUM(amount) FROM expenses WHERE company_id=c.id AND strftime('%Y-%m',created_at)=?), 0) as month_exp,
               IFNULL((SELECT SUM(amount) FROM expenses WHERE company_id=c.id), 0) as total_exp,
               (SELECT username FROM users WHERE company_id=c.id AND role='director' LIMIT 1) as director
        FROM companies c ORDER BY c.balance DESC
    """, (MONTH,))
    companies = c.fetchall()

    c.execute("""
        SELECT e.amount, e.description, e.created_at, c.name as company,
               u.username as director, c.id as company_id
        FROM expenses e
        JOIN companies c ON e.company_id=c.id
        LEFT JOIN users u ON e.user_id=u.id
        WHERE date(e.created_at)=date('now')
        ORDER BY c.name, e.created_at DESC
    """)
    today_expenses = c.fetchall()

    c.execute("SELECT IFNULL(SUM(balance),0) FROM companies")
    total_balance = c.fetchone()[0]
    c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses WHERE date(created_at)=date('now')")
    total_today = c.fetchone()[0]
    c.execute("SELECT IFNULL(SUM(amount),0) FROM expenses WHERE strftime('%Y-%m',created_at)=?", (MONTH,))
    total_month = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM companies")
    companies_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE role='director'")
    directors_count = c.fetchone()[0]
    try:
        c.execute("SELECT COUNT(*) FROM workers WHERE status='active'")
        workers_count = c.fetchone()[0]
    except:
        workers_count = 0

    conn.close()
    return dict(companies=companies, today_expenses=today_expenses,
                total_balance=total_balance, total_today=total_today,
                total_month=total_month, companies_count=companies_count,
                directors_count=directors_count, workers_count=workers_count)


def send_telegram_message(text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print("Telegram xato:", e)


def send_telegram_file(file_bytes, filename, caption):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
                      data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                      files={"document": (filename, file_bytes)}, timeout=30)
    except Exception as e:
        print("Fayl yuborish xato:", e)


def send_daily_telegram(data):
    lines = ""
    for comp in data["companies"]:
        bal_color = "🟢" if comp["balance"] > 0 else "🔴"
        lines += (f"\n{bal_color} <b>{comp['name']}</b> "
                  f"{'· 👔 ' + comp['director'] if comp['director'] else ''}\n"
                  f"   💰 Balans: <code>{comp['balance']:,} so'm</code>\n"
                  f"   ☀️ Bugun: <code>{comp['today_exp']:,} so'm</code>\n"
                  f"   📅 Oy: <code>{comp['month_exp']:,} so'm</code>\n")

    send_telegram_message(
        f"╔══════════════════════╗\n"
        f"║  📊  <b>KUNLIK HISOBOT</b>  📊  ║\n"
        f"╚══════════════════════╝\n\n"
        f"📅 <b>Sana:</b> {TODAY}\n"
        f"🕚 <b>Vaqt:</b> 23:00 (Toshkent)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>UMUMIY</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 Jami balans: <code>{data['total_balance']:,} so'm</code>\n"
        f"☀️ Bugungi xarajat: <code>{data['total_today']:,} so'm</code>\n"
        f"📅 Oylik xarajat: <code>{data['total_month']:,} so'm</code>\n"
        f"🏢 Kompaniyalar: <b>{data['companies_count']}</b>\n"
        f"👔 Direktorlar: <b>{data['directors_count']}</b>\n"
        f"👷 Faol ishchilar: <b>{data['workers_count']}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏢 <b>KOMPANIYALAR</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
        f"{lines}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💸 Bugun <b>{len(data['today_expenses'])}</b> ta xarajat\n"
        f"📎 Excel va PDF quyida 👇"
    )


# ===== STIL YORDAMCHILARI =====
def hdr(text, ws, row, col, end_col, bg="1E3A5F", fg="FFFFFF", size=11, height=22):
    ws.merge_cells(f"{get_column_letter(col)}{row}:{get_column_letter(end_col)}{row}")
    cell = ws.cell(row=row, column=col, value=text)
    cell.fill = PatternFill("solid", fgColor=bg)
    cell.font = Font(bold=True, color=fg, size=size, name="Arial")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = height
    return cell

def styled(cell, bold=False, color="000000", bg=None, align="left", size=10, wrap=False, fmt=None):
    cell.font = Font(bold=bold, color=color, size=size, name="Arial")
    cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
    if bg:
        cell.fill = PatternFill("solid", fgColor=bg)
    if fmt:
        cell.number_format = fmt
    return cell

def border_all(ws, min_row, max_row, min_col, max_col, color="D0D7E3"):
    side = Side(style="thin", color=color)
    b = Border(left=side, right=side, top=side, bottom=side)
    for row in ws.iter_rows(min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col):
        for cell in row:
            cell.border = b


def create_excel(data):
    wb = Workbook()

    # ======== 1. UMUMIY HISOBOT SHEET ========
    ws = wb.active
    ws.title = "📊 Umumiy Hisobot"
    ws.sheet_view.showGridLines = False

    # Logo va sarlavha
    hdr(f"📊  KUNLIK MOLIYAVIY HISOBOT", ws, 1, 1, 6, bg="0F2044", size=14, height=36)
    hdr(f"Sana: {TODAY}  |  Vaqt: {NOW}  |  {MONTH_NAME}", ws, 2, 1, 6, bg="1A3A6B", fg="BDD7EE", size=10, height=20)

    # KPI kartalar
    ws.row_dimensions[4].height = 18
    kpis = [
        ("💳 JAMI BALANS", data["total_balance"], "16A34A"),
        ("☀️ BUGUNGI XARAJAT", data["total_today"], "DC2626"),
        ("📅 OYLIK XARAJAT", data["total_month"], "D97706"),
        ("🏢 KOMPANIYALAR", data["companies_count"], "3B6EF6"),
        ("👔 DIREKTORLAR", data["directors_count"], "7C3AED"),
        ("👷 ISHCHILAR", data["workers_count"], "059669"),
    ]
    for i, (label, val, clr) in enumerate(kpis):
        col = i + 1
        ws.column_dimensions[get_column_letter(col)].width = 22
        ws.cell(row=4, column=col, value=label).font = Font(bold=True, color=clr, size=9, name="Arial")
        ws.cell(row=4, column=col).alignment = Alignment(horizontal="center")
        v_cell = ws.cell(row=5, column=col, value=val)
        v_cell.font = Font(bold=True, color=clr, size=16, name="Arial")
        v_cell.alignment = Alignment(horizontal="center", vertical="center")
        v_cell.fill = PatternFill("solid", fgColor="F8FAFF")
        if i < 3:
            v_cell.number_format = '#,##0 "so\'m"'
        ws.row_dimensions[5].height = 32
        ws.cell(row=4, column=col).fill = PatternFill("solid", fgColor="F0F4FF")

    border_all(ws, 4, 5, 1, 6)

    # Kompaniyalar jadvali
    ws.row_dimensions[7].height = 14
    hdr("🏢  KOMPANIYALAR BALANSI VA XARAJATLAR", ws, 8, 1, 6, bg="0F2044", size=11, height=28)

    col_heads = ["#", "Kompaniya", "Direktor", "Joriy Balans", "Bugungi Xarajat", "Oylik Xarajat"]
    col_widths = [5, 26, 18, 22, 22, 22]
    for j, (h, w) in enumerate(zip(col_heads, col_widths), 1):
        cell = ws.cell(row=9, column=j, value=h)
        styled(cell, bold=True, color="FFFFFF", bg="1E3A5F", align="center", size=10)
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[9].height = 20

    for i, comp in enumerate(data["companies"], 1):
        row = 9 + i
        bg = "F0F7FF" if i % 2 == 0 else "FFFFFF"
        vals = [i, comp["name"], comp["director"] or "—",
                comp["balance"], comp["today_exp"], comp["month_exp"]]
        for j, v in enumerate(vals, 1):
            cell = ws.cell(row=row, column=j, value=v)
            align = "center" if j in [1, 3] else ("right" if j >= 4 else "left")
            styled(cell, bg=bg, align=align, size=10)
            if j >= 4:
                cell.number_format = '#,##0'
                if j == 3 and comp["balance"] <= 0:
                    cell.font = Font(bold=True, color="DC2626", size=10, name="Arial")
        ws.row_dimensions[row].height = 18

    last_data_row = 9 + len(data["companies"])
    # Jami qator
    total_row = last_data_row + 1
    ws.cell(row=total_row, column=2, value="JAMI").font = Font(bold=True, size=10, name="Arial")
    ws.cell(row=total_row, column=2).fill = PatternFill("solid", fgColor="E8F4FD")
    for col_idx, key in [(4, "total_balance"), (5, "total_today"), (6, "total_month")]:
        cell = ws.cell(row=total_row, column=col_idx, value=data[key])
        cell.font = Font(bold=True, color="0F2044", size=11, name="Arial")
        cell.number_format = '#,##0'
        cell.alignment = Alignment(horizontal="right", vertical="center")
        cell.fill = PatternFill("solid", fgColor="E8F4FD")
    ws.row_dimensions[total_row].height = 22

    border_all(ws, 9, total_row, 1, 6)

    # Bugungi xarajatlar
    start = total_row + 2
    hdr("💸  BUGUNGI XARAJATLAR", ws, start, 1, 6, bg="7F1D1D", fg="FFFFFF", size=11, height=28)

    exp_heads = ["#", "Vaqt", "Kompaniya", "Direktor", "Summa", "Izoh"]
    exp_widths = [5, 18, 24, 18, 20, 35]
    for j, (h, w) in enumerate(zip(exp_heads, exp_widths), 1):
        cell = ws.cell(row=start+1, column=j, value=h)
        styled(cell, bold=True, color="FFFFFF", bg="991B1B", align="center", size=10)
        ws.column_dimensions[get_column_letter(j)].width = max(ws.column_dimensions[get_column_letter(j)].width, w)
    ws.row_dimensions[start+1].height = 20

    if data["today_expenses"]:
        for i, exp in enumerate(data["today_expenses"], 1):
            row = start + 1 + i
            bg = "FFF5F5" if i % 2 == 0 else "FFFFFF"
            vals = [i, str(exp["created_at"])[:16], exp["company"],
                    exp["director"] or "—", exp["amount"], exp["description"] or "—"]
            for j, v in enumerate(vals, 1):
                align = "center" if j in [1, 2, 4] else ("right" if j == 5 else "left")
                cell = ws.cell(row=row, column=j, value=v)
                styled(cell, bg=bg, align=align, size=9)
                if j == 5:
                    cell.number_format = '#,##0'
            ws.row_dimensions[row].height = 16

        exp_total_row = start + 1 + len(data["today_expenses"]) + 1
        ws.cell(row=exp_total_row, column=4, value="JAMI:").font = Font(bold=True, size=10, name="Arial")
        t_cell = ws.cell(row=exp_total_row, column=5, value=data["total_today"])
        t_cell.font = Font(bold=True, color="DC2626", size=11, name="Arial")
        t_cell.number_format = '#,##0'
        t_cell.alignment = Alignment(horizontal="right")
        for col_i in range(1, 7):
            ws.cell(row=exp_total_row, column=col_i).fill = PatternFill("solid", fgColor="FFE4E4")
        border_all(ws, start+1, exp_total_row, 1, 6)
    else:
        ws.cell(row=start+2, column=1, value="Bugun xarajat yo'q").font = Font(italic=True, color="999999", name="Arial")
        ws.merge_cells(f"A{start+2}:F{start+2}")

    # ======== 2. HAR BIR KOMPANIYA UCHUN ALOHIDA SHEET ========
    for comp in data["companies"]:
        safe_name = comp["name"][:28] if comp["name"] else "Kompaniya"
        wc = wb.create_sheet(f"🏢 {safe_name}")
        wc.sheet_view.showGridLines = False

        hdr(f"🏢  {comp['name'].upper()}", wc, 1, 1, 5, bg="0F2044", size=13, height=34)
        hdr(f"Kunlik hisobot  |  {TODAY}  |  Direktor: {comp['director'] or '—'}",
            wc, 2, 1, 5, bg="1A3A6B", fg="BDD7EE", size=10, height=20)

        # Kompaniya KPI
        wc.row_dimensions[4].height = 18
        comp_kpis = [
            ("💰 JORIY BALANS", comp["balance"], "16A34A" if comp["balance"] > 0 else "DC2626"),
            ("☀️ BUGUNGI XARAJAT", comp["today_exp"], "DC2626"),
            ("📅 OYLIK XARAJAT", comp["month_exp"], "D97706"),
            ("📊 JAMI XARAJAT", comp["total_exp"], "3B6EF6"),
        ]
        for i, (label, val, clr) in enumerate(comp_kpis):
            col = i + 1
            wc.column_dimensions[get_column_letter(col)].width = 25
            wc.cell(row=4, column=col, value=label).font = Font(bold=True, color=clr, size=9, name="Arial")
            wc.cell(row=4, column=col).alignment = Alignment(horizontal="center")
            wc.cell(row=4, column=col).fill = PatternFill("solid", fgColor="F0F4FF")
            v = wc.cell(row=5, column=col, value=val)
            v.font = Font(bold=True, color=clr, size=15, name="Arial")
            v.alignment = Alignment(horizontal="center", vertical="center")
            v.fill = PatternFill("solid", fgColor="F8FAFF")
            v.number_format = '#,##0 "so\'m"'
            wc.row_dimensions[5].height = 30

        wc.column_dimensions["E"].width = 5
        border_all(wc, 4, 5, 1, 4)

        # Bu kompaniyaning bugungi xarajatlari
        comp_exps = [e for e in data["today_expenses"] if e["company_id"] == comp["id"]]
        wc.row_dimensions[7].height = 14
        hdr(f"☀️  BUGUNGI XARAJATLAR  ({len(comp_exps)} ta)",
            wc, 8, 1, 5, bg="7F1D1D", size=11, height=26)

        heads = ["#", "Vaqt", "Direktor", "Summa (so'm)", "Izoh"]
        widths = [5, 20, 18, 20, 40]
        for j, (h, w) in enumerate(zip(heads, widths), 1):
            cell = wc.cell(row=9, column=j, value=h)
            styled(cell, bold=True, color="FFFFFF", bg="991B1B", align="center", size=10)
            wc.column_dimensions[get_column_letter(j)].width = w
        wc.row_dimensions[9].height = 20

        if comp_exps:
            for i, exp in enumerate(comp_exps, 1):
                row = 9 + i
                bg = "FFF5F5" if i % 2 == 0 else "FFFFFF"
                vals = [i, str(exp["created_at"])[:16], exp["director"] or "—",
                        exp["amount"], exp["description"] or "—"]
                for j, v in enumerate(vals, 1):
                    cell = wc.cell(row=row, column=j, value=v)
                    align = "center" if j in [1, 2, 3] else ("right" if j == 4 else "left")
                    styled(cell, bg=bg, align=align, size=9)
                    if j == 4:
                        cell.number_format = '#,##0'
                wc.row_dimensions[row].height = 16

            tr = 9 + len(comp_exps) + 1
            wc.cell(row=tr, column=3, value="JAMI:").font = Font(bold=True, size=10, name="Arial")
            tc = wc.cell(row=tr, column=4, value=comp["today_exp"])
            tc.font = Font(bold=True, color="DC2626", size=11, name="Arial")
            tc.number_format = '#,##0'
            tc.alignment = Alignment(horizontal="right")
            for ci in range(1, 6):
                wc.cell(row=tr, column=ci).fill = PatternFill("solid", fgColor="FFE4E4")
            border_all(wc, 9, tr, 1, 5)
        else:
            wc.cell(row=10, column=1, value="Bugun xarajat yo'q").font = Font(italic=True, color="999999", name="Arial")
            wc.merge_cells("A10:E10")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ===== PDF =====
def create_pdf(data):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    def h1(text): return Paragraph(text, ParagraphStyle('h1', parent=styles['Normal'],
        fontSize=18, fontName='Helvetica-Bold', textColor=colors.HexColor('#0f2044'), spaceAfter=4))
    def h2(text): return Paragraph(text, ParagraphStyle('h2', parent=styles['Normal'],
        fontSize=12, fontName='Helvetica-Bold', textColor=colors.HexColor('#1e3a5f'), spaceAfter=6, spaceBefore=10))
    def sub(text): return Paragraph(text, ParagraphStyle('sub', parent=styles['Normal'],
        fontSize=9, textColor=colors.HexColor('#64748b'), spaceAfter=10))

    def tbl(data_rows, col_widths, header_bg=colors.HexColor('#0f2044')):
        t = Table(data_rows, colWidths=col_widths)
        row_bgs = []
        for i in range(1, len(data_rows)):
            bg = colors.HexColor('#f0f7ff') if i % 2 == 0 else colors.white
            row_bgs.append(('BACKGROUND', (0, i), (-1, i), bg))
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), header_bg),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 8.5),
            ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dee4f0')),
            ('PADDING', (0,0), (-1,-1), 6),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ] + row_bgs))
        return t

    story = []

    # Sarlavha
    story.append(h1("KUNLIK MOLIYAVIY HISOBOT"))
    story.append(sub(f"Sana: {TODAY}   |   Vaqt: {NOW} (Toshkent)   |   {MONTH_NAME}"))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#3b6ef6')))
    story.append(Spacer(1, 10))

    # KPI jadvali
    story.append(h2("Umumiy Ko'rsatkichlar"))
    kpi_data = [
        ["Ko'rsatkich", "Qiymat", "Ko'rsatkich", "Qiymat"],
        ["💳 Jami balans", f"{data['total_balance']:,} so'm",
         "🏢 Kompaniyalar", str(data['companies_count'])],
        ["☀️ Bugungi xarajat", f"{data['total_today']:,} so'm",
         "👔 Direktorlar", str(data['directors_count'])],
        ["📅 Oylik xarajat", f"{data['total_month']:,} so'm",
         "👷 Faol ishchilar", str(data['workers_count'])],
    ]
    kt = Table(kpi_data, colWidths=[5*cm, 5*cm, 5*cm, 3*cm])
    kt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f2044')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f7ff'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dee4f0')),
        ('PADDING', (0,0), (-1,-1), 7),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('ALIGN', (1,1), (1,-1), 'RIGHT'),
        ('ALIGN', (3,1), (3,-1), 'RIGHT'),
        ('FONTNAME', (1,1), (1,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1,1), (1,1), colors.HexColor('#16a34a')),
        ('TEXTCOLOR', (1,2), (1,2), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (1,3), (1,3), colors.HexColor('#d97706')),
    ]))
    story.append(kt)
    story.append(Spacer(1, 12))

    # Kompaniyalar balansi
    story.append(h2("Kompaniyalar Balansi"))
    comp_rows = [["#", "Kompaniya", "Direktor", "Balans", "Bugun", "Oy"]]
    for i, comp in enumerate(data["companies"], 1):
        comp_rows.append([
            str(i), comp["name"], comp["director"] or "—",
            f"{comp['balance']:,}", f"{comp['today_exp']:,}", f"{comp['month_exp']:,}"
        ])
    comp_rows.append(["", "JAMI", "",
                       f"{data['total_balance']:,}",
                       f"{data['total_today']:,}",
                       f"{data['total_month']:,}"])

    ct = tbl(comp_rows, [0.8*cm, 5*cm, 3.5*cm, 3.2*cm, 2.8*cm, 2.7*cm])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f2044')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8.5),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.HexColor('#f0f7ff'), colors.white]),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#e0ecff')),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dee4f0')),
        ('ALIGN', (3,0), (5,-1), 'RIGHT'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('FONTNAME', (0,1), (2,-1), 'Helvetica'),
    ]))
    story.append(ct)

    # Har bir kompaniya alohida sahifa
    for comp in data["companies"]:
        story.append(PageBreak())
        story.append(h1(f"🏢 {comp['name']}"))
        story.append(sub(f"Direktor: {comp['director'] or '—'}   |   {TODAY}"))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3b6ef6')))
        story.append(Spacer(1, 8))

        # Kompaniya KPI
        ckpi = [
            ["💰 Joriy Balans", "☀️ Bugungi Xarajat", "📅 Oylik Xarajat", "📊 Jami Xarajat"],
            [f"{comp['balance']:,} so'm", f"{comp['today_exp']:,} so'm",
             f"{comp['month_exp']:,} so'm", f"{comp['total_exp']:,} so'm"],
        ]
        ckt = Table(ckpi, colWidths=[4.5*cm, 4.5*cm, 4.5*cm, 4.5*cm])
        bal_color = colors.HexColor('#16a34a') if comp["balance"] > 0 else colors.HexColor('#dc2626')
        ckt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e3a5f')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#f8faff')),
            ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0,1), (0,1), bal_color),
            ('TEXTCOLOR', (1,1), (1,1), colors.HexColor('#dc2626')),
            ('TEXTCOLOR', (2,1), (2,1), colors.HexColor('#d97706')),
            ('TEXTCOLOR', (3,1), (3,1), colors.HexColor('#3b6ef6')),
            ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dee4f0')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('PADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(ckt)
        story.append(Spacer(1, 10))

        # Bugungi xarajatlar
        comp_exps = [e for e in data["today_expenses"] if e["company_id"] == comp["id"]]
        story.append(h2(f"Bugungi Xarajatlar  ({len(comp_exps)} ta)"))

        if comp_exps:
            exp_rows = [["#", "Vaqt", "Direktor", "Summa", "Izoh"]]
            for i, exp in enumerate(comp_exps, 1):
                desc = str(exp["description"] or "")[:40]
                exp_rows.append([str(i), str(exp["created_at"])[:16],
                                  exp["director"] or "—", f"{exp['amount']:,}", desc])
            exp_rows.append(["", "", "JAMI", f"{comp['today_exp']:,}", ""])
            et = tbl(exp_rows, [0.8*cm, 3.5*cm, 3*cm, 3*cm, 7.7*cm],
                     header_bg=colors.HexColor('#7f1d1d'))
            et.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#7f1d1d')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 8.5),
                ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.HexColor('#fff5f5'), colors.white]),
                ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#ffe4e4')),
                ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
                ('TEXTCOLOR', (3,-1), (3,-1), colors.HexColor('#dc2626')),
                ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#fecaca')),
                ('ALIGN', (3,0), (3,-1), 'RIGHT'),
                ('ALIGN', (0,0), (0,-1), 'CENTER'),
                ('PADDING', (0,0), (-1,-1), 6),
                ('FONTNAME', (0,1), (-1,-2), 'Helvetica'),
            ]))
            story.append(et)
        else:
            story.append(Paragraph("Bugun xarajat amalga oshirilmagan.",
                          ParagraphStyle('empty', parent=styles['Normal'],
                          fontSize=10, textColor=colors.HexColor('#94a3b8'), spaceAfter=8)))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def main():
    print(f"[{NOW}] Kunlik hisobot yuborilmoqda...")
    data = get_report_data()
    send_daily_telegram(data)
    excel_bytes = create_excel(data)
    send_telegram_file(excel_bytes, f"hisobot_{TODAY}.xlsx", f"📊 Excel hisobot — {TODAY}")
    pdf_bytes = create_pdf(data)
    send_telegram_file(pdf_bytes, f"hisobot_{TODAY}.pdf", f"📄 PDF hisobot — {TODAY}")
    print(f"[{NOW}] Hisobot muvaffaqiyatli yuborildi!")


if __name__ == "__main__":
    main()