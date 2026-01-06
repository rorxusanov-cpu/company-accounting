import sqlite3
conn = sqlite3.connect("users.db")
c = conn.cursor()
c.execute("PRAGMA table_info(expenses)")
print(c.fetchall())
conn.close()
exit()



print("OK ✅ user_id ustuni qo‘shildi")
