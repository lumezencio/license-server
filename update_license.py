"""
Script para alterar data de expiração da licença
"""
import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('licenses.db')
cur = conn.cursor()

# Mostrar licença atual
cur.execute("SELECT license_key, expires_at, status FROM licenses")
print("\n=== LICENÇAS ATUAIS ===")
for row in cur.fetchall():
    print(f"  {row[0]} - Expira: {row[1]} - Status: {row[2]}")

# Opções de teste
print("\n=== OPÇÕES ===")
print("1. Expirar em 1 minuto (testar expiração)")
print("2. Expirar em 1 hora")
print("3. Expirar em 1 dia")
print("4. Expirar em 7 dias")
print("5. Expirar em 30 dias")
print("6. Expirar em 1 ano (padrão)")
print("7. JÁ EXPIRADA (para testar bloqueio)")
print("0. Sair sem alterar")

opcao = input("\nEscolha uma opção: ")

if opcao == "0":
    print("Saindo...")
elif opcao in ["1", "2", "3", "4", "5", "6", "7"]:
    deltas = {
        "1": timedelta(minutes=1),
        "2": timedelta(hours=1),
        "3": timedelta(days=1),
        "4": timedelta(days=7),
        "5": timedelta(days=30),
        "6": timedelta(days=365),
        "7": timedelta(days=-1),  # Já expirada
    }

    new_expires = datetime.utcnow() + deltas[opcao]

    cur.execute(
        "UPDATE licenses SET expires_at = ? WHERE license_key = ?",
        (new_expires.isoformat(), "MJ67-MSD2-DNP6-R6FG")
    )
    conn.commit()

    print(f"\n✅ Licença atualizada!")
    print(f"   Nova expiração: {new_expires.strftime('%d/%m/%Y %H:%M:%S')}")

    if opcao == "7":
        print("\n⚠️  LICENÇA JÁ EXPIRADA - O sistema deve bloquear o acesso!")
else:
    print("Opção inválida")

conn.close()
