import sqlite3
conn = sqlite3.connect('licenses.db')
cursor = conn.cursor()
cursor.execute("SELECT * FROM admin_users")
for row in cursor.fetchall():
    print(row)
conn.close()
