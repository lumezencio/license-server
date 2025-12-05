import sqlite3

conn = sqlite3.connect('licenses.db')
cur = conn.cursor()

print("=== Tabelas ===")
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(f"  - {t[0]}")

print("\n=== Licenças ===")
try:
    licenses = cur.execute("SELECT id, license_key, plan, status, expires_at FROM licenses").fetchall()
    for lic in licenses:
        print(f"  {lic[1]} | {lic[2]} | {lic[3]} | {lic[4]}")
except Exception as e:
    print(f"  Erro: {e}")

print("\n=== Clientes ===")
try:
    clients = cur.execute("SELECT id, name, email FROM clients").fetchall()
    for c in clients:
        print(f"  {c[0][:8]}... | {c[1]} | {c[2]}")
except Exception as e:
    print(f"  Erro: {e}")

print("\n=== Admin Users ===")
try:
    admins = cur.execute("SELECT id, email, name FROM admin_users").fetchall()
    for a in admins:
        print(f"  {a[0][:8]}... | {a[1]} | {a[2]}")
except Exception as e:
    print(f"  Erro: {e}")

conn.close()
