"""
Script para criar dados de teste no License Server
Execute: python setup_test_data.py
"""
import httpx
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8090"

def main():
    print("=== Setup de Dados de Teste ===\n")

    # 1. Login
    print("1. Fazendo login...")
    login_response = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@license-server.com", "password": "admin123"}
    )

    if login_response.status_code != 200:
        print(f"Erro no login: {login_response.text}")
        return

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"   Token obtido!")

    # 2. Criar cliente
    print("\n2. Criando cliente de teste...")
    client_response = httpx.post(
        f"{BASE_URL}/api/clients",
        json={
            "name": "Empresa Teste LTDA",
            "email": "contato@empresateste.com",
            "document": "12345678000199",
            "phone": "(11) 99999-9999",
            "contact_name": "João Silva",
            "city": "São Paulo",
            "state": "SP"
        },
        headers=headers
    )

    if client_response.status_code == 201:
        client = client_response.json()
        client_id = client["id"]
        print(f"   Cliente criado: {client['name']} (ID: {client_id})")
    elif client_response.status_code == 400 and "already" in client_response.text.lower():
        print("   Cliente já existe, buscando...")
        clients = httpx.get(f"{BASE_URL}/api/clients", headers=headers).json()
        client_id = clients[0]["id"] if clients else None
        if not client_id:
            print("Erro: nenhum cliente encontrado")
            return
    else:
        print(f"Erro ao criar cliente: {client_response.text}")
        return

    # 3. Criar licença
    print("\n3. Criando licença de teste...")
    expires_at = (datetime.utcnow() + timedelta(days=365)).isoformat()

    license_response = httpx.post(
        f"{BASE_URL}/api/licenses",
        json={
            "client_id": client_id,
            "plan": "professional",
            "features": ["reports", "multi_user", "api_access", "support"],
            "max_users": 10,
            "max_customers": 1000,
            "max_products": 5000,
            "max_monthly_transactions": 10000,
            "expires_at": expires_at,
            "is_trial": False,
            "notes": "Licença de teste"
        },
        headers=headers
    )

    if license_response.status_code == 201:
        license_data = license_response.json()
        print(f"   Licença criada!")
        print(f"\n{'='*50}")
        print(f"   CHAVE DE LICENÇA: {license_data['license_key']}")
        print(f"{'='*50}")
        print(f"   Plano: {license_data['plan']}")
        print(f"   Expira em: {license_data['expires_at'][:10]}")
        print(f"   Max Usuários: {license_data['max_users']}")
    else:
        print(f"Erro ao criar licença: {license_response.text}")
        return

    # 4. Verificar endpoint de validação
    print("\n4. Testando endpoint público de validação...")
    health = httpx.get(f"{BASE_URL}/api/v1/health")
    print(f"   Health check: {health.json()}")

    print("\n=== Setup Completo! ===")
    print(f"\nUse a chave acima para ativar no enterprise_system")
    print(f"Acesse: http://localhost:5173/license")


if __name__ == "__main__":
    main()
