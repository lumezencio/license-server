import sqlite3

conn = sqlite3.connect('licenses.db')
cur = conn.cursor()

print("=== TENANT lucianomezencio@gmail.com ===")
cur.execute("""
SELECT
    tenant_code, email, status, provisioned_at,
    database_name, database_host, database_port, database_user, database_password,
    is_trial, password_changed
FROM tenants
WHERE email = 'lucianomezencio@gmail.com'
""")
row = cur.fetchone()
if row:
    print(f"tenant_code: {row[0]}")
    print(f"email: {row[1]}")
    print(f"status: {row[2]}")
    print(f"provisioned_at: {row[3]}")
    print(f"database_name: {row[4]}")
    print(f"database_host: {row[5]}")
    print(f"database_port: {row[6]}")
    print(f"database_user: {row[7]}")
    print(f"database_password: {row[8]}")
    print(f"is_trial: {row[9]}")
    print(f"password_changed: {row[10]}")
else:
    print("Tenant nao encontrado!")

conn.close()
