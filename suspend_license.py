import sqlite3
import sys

conn = sqlite3.connect('licenses.db')
cursor = conn.cursor()

if len(sys.argv) > 1 and sys.argv[1] == 'suspend':
    cursor.execute("UPDATE licenses SET status='suspended' WHERE license_key='TLSV-AWMZ-R589-M933'")
    conn.commit()
    print('Licenca suspensa!')
elif len(sys.argv) > 1 and sys.argv[1] == 'active':
    cursor.execute("UPDATE licenses SET status='active' WHERE license_key='TLSV-AWMZ-R589-M933'")
    conn.commit()
    print('Licenca reativada!')
else:
    print('Status atual:')

cursor.execute("SELECT license_key, status FROM licenses")
for row in cursor.fetchall():
    print(f'  {row}')
conn.close()
