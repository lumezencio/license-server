import sqlite3

conn = sqlite3.connect('licenses.db')
cur = conn.cursor()

print("=== LICENSES ===")
cur.execute("SELECT license_key, client_id, plan, status, is_trial, expires_at FROM licenses")
for r in cur.fetchall():
    print(r)

print("\n=== CLIENTS ===")
cur.execute("SELECT id, name, email FROM clients")
for r in cur.fetchall():
    print(r)

conn.close()
