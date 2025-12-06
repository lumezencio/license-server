# setup_local_tenant.py - Configura tenant local para teste
import sqlite3
import hashlib
from datetime import datetime

conn = sqlite3.connect('licenses.db')
cursor = conn.cursor()

# Atualiza o tenant existente para usar o email admin@empresa.com
# que ja existe no banco enterprise_db local
cursor.execute('''
UPDATE tenants
SET status = 'active',
    provisioned_at = ?,
    database_host = 'localhost',
    database_port = 5432,
    database_user = 'enterprise_user',
    database_password = '#otopodomundo2025',
    database_name = 'enterprise_db',
    password_changed = 1,
    is_trial = 0,
    email = 'admin@empresa.com'
WHERE tenant_code = '12345678909'
''', (datetime.now().isoformat(),))

conn.commit()

# Verifica
cursor.execute("SELECT email, status, provisioned_at, database_name, database_host, database_user FROM tenants WHERE tenant_code = '12345678909'")
print('Tenant atualizado:', cursor.fetchone())
conn.close()
print('Pronto! Tenant configurado para usar admin@empresa.com no banco enterprise_db local')
