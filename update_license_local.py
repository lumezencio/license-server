# update_license_local.py - Atualiza licenca local para teste
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('licenses.db')
cur = conn.cursor()

# Atualiza a licenca do tenant local para professional ativa
client_id = '62ccacf7-ae4d-4492-9c2a-e23cd666384a'
expires_at = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d %H:%M:%S')

cur.execute('''
UPDATE licenses
SET plan = 'professional',
    status = 'active',
    is_trial = 0,
    expires_at = ?
WHERE client_id = ?
''', (expires_at, client_id))

conn.commit()

# Verifica
cur.execute("SELECT license_key, client_id, plan, status, is_trial, expires_at FROM licenses WHERE client_id = ?", (client_id,))
print('Licenca atualizada:', cur.fetchone())

conn.close()
print('Pronto! Licenca configurada como Professional com 365 dias')
