"""
License Server - CLI Admin
Ferramenta de linha de comando para gerenciar licenças

Uso:
    python admin_cli.py login
    python admin_cli.py clients list
    python admin_cli.py clients create "Nome da Empresa" "email@empresa.com"
    python admin_cli.py licenses list
    python admin_cli.py licenses create <client_id> <plano> <dias>
    python admin_cli.py licenses revoke <license_key>
"""
import sys
import json
import httpx
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL = "http://localhost:8090"
TOKEN_FILE = Path(".admin_token")


def save_token(token: str):
    TOKEN_FILE.write_text(token)


def load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    return None


def get_headers():
    token = load_token()
    if not token:
        print("Erro: Faça login primeiro com 'python admin_cli.py login'")
        sys.exit(1)
    return {"Authorization": f"Bearer {token}"}


def cmd_login():
    """Login no sistema"""
    email = input("Email [admin@license-server.com]: ").strip() or "admin@license-server.com"
    password = input("Senha [admin123]: ").strip() or "admin123"

    try:
        response = httpx.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            save_token(data["access_token"])
            print(f"\n✓ Login bem sucedido!")
            print(f"  Usuário: {data['user']['email']}")
        else:
            print(f"✗ Erro: {response.json().get('detail', 'Falha no login')}")
    except Exception as e:
        print(f"✗ Erro de conexão: {e}")


def cmd_clients_list():
    """Lista clientes"""
    try:
        response = httpx.get(f"{BASE_URL}/api/clients", headers=get_headers())
        if response.status_code == 200:
            clients = response.json()
            print(f"\n{'='*70}")
            print(f"{'ID':<36} | {'Nome':<20} | {'Email':<20}")
            print(f"{'='*70}")
            for c in clients:
                print(f"{c['id']:<36} | {c['name'][:20]:<20} | {c['email'][:20]:<20}")
            print(f"\nTotal: {len(clients)} clientes")
        else:
            print(f"✗ Erro: {response.text}")
    except Exception as e:
        print(f"✗ Erro: {e}")


def cmd_clients_create(name: str, email: str):
    """Cria novo cliente"""
    try:
        response = httpx.post(
            f"{BASE_URL}/api/clients",
            json={"name": name, "email": email},
            headers=get_headers()
        )
        if response.status_code == 201:
            client = response.json()
            print(f"\n✓ Cliente criado!")
            print(f"  ID: {client['id']}")
            print(f"  Nome: {client['name']}")
            print(f"  Email: {client['email']}")
        else:
            print(f"✗ Erro: {response.json().get('detail', response.text)}")
    except Exception as e:
        print(f"✗ Erro: {e}")


def cmd_licenses_list():
    """Lista licenças"""
    try:
        response = httpx.get(f"{BASE_URL}/api/licenses", headers=get_headers())
        if response.status_code == 200:
            licenses = response.json()
            print(f"\n{'='*90}")
            print(f"{'Chave':<19} | {'Cliente':<20} | {'Plano':<12} | {'Status':<10} | {'Expira':<10}")
            print(f"{'='*90}")
            for lic in licenses:
                client_name = (lic.get('client_name') or 'N/A')[:20]
                expires = lic['expires_at'][:10] if lic.get('expires_at') else 'N/A'
                print(f"{lic['license_key']:<19} | {client_name:<20} | {lic['plan']:<12} | {lic['status']:<10} | {expires:<10}")
            print(f"\nTotal: {len(licenses)} licenças")
        else:
            print(f"✗ Erro: {response.text}")
    except Exception as e:
        print(f"✗ Erro: {e}")


def cmd_licenses_create(client_id: str, plan: str = "professional", days: int = 365):
    """Cria nova licença"""
    expires_at = (datetime.utcnow() + timedelta(days=int(days))).isoformat()

    plans_config = {
        "starter": {"max_users": 3, "max_customers": 100, "max_products": 500},
        "professional": {"max_users": 10, "max_customers": 1000, "max_products": 5000},
        "enterprise": {"max_users": 50, "max_customers": 10000, "max_products": 50000},
        "unlimited": {"max_users": 999, "max_customers": 999999, "max_products": 999999},
    }

    config = plans_config.get(plan, plans_config["professional"])

    try:
        response = httpx.post(
            f"{BASE_URL}/api/licenses",
            json={
                "client_id": client_id,
                "plan": plan,
                "features": ["reports", "multi_user", "api_access"],
                "max_users": config["max_users"],
                "max_customers": config["max_customers"],
                "max_products": config["max_products"],
                "max_monthly_transactions": 100000,
                "expires_at": expires_at,
                "is_trial": False
            },
            headers=get_headers()
        )
        if response.status_code == 201:
            lic = response.json()
            print(f"\n{'='*50}")
            print(f"  ✓ LICENÇA CRIADA COM SUCESSO!")
            print(f"{'='*50}")
            print(f"  Chave: {lic['license_key']}")
            print(f"  Plano: {lic['plan']}")
            print(f"  Expira: {lic['expires_at'][:10]}")
            print(f"  Max Usuários: {lic['max_users']}")
            print(f"{'='*50}")
            print(f"\n  Envie esta chave para o cliente!")
        else:
            print(f"✗ Erro: {response.json().get('detail', response.text)}")
    except Exception as e:
        print(f"✗ Erro: {e}")


def cmd_licenses_revoke(license_key: str):
    """Revoga uma licença"""
    # Primeiro busca a licença pelo key
    try:
        response = httpx.get(f"{BASE_URL}/api/licenses?search={license_key}", headers=get_headers())
        if response.status_code == 200:
            licenses = response.json()
            if not licenses:
                print(f"✗ Licença não encontrada: {license_key}")
                return

            license_id = licenses[0]['id']

            # Revoga
            response = httpx.post(
                f"{BASE_URL}/api/licenses/{license_id}/revoke",
                headers=get_headers()
            )
            if response.status_code == 200:
                print(f"✓ Licença {license_key} revogada com sucesso!")
            else:
                print(f"✗ Erro: {response.text}")
        else:
            print(f"✗ Erro: {response.text}")
    except Exception as e:
        print(f"✗ Erro: {e}")


def cmd_stats():
    """Mostra estatísticas"""
    try:
        response = httpx.get(f"{BASE_URL}/api/stats/dashboard", headers=get_headers())
        if response.status_code == 200:
            stats = response.json()
            print(f"\n{'='*40}")
            print(f"  ESTATÍSTICAS DO LICENSE SERVER")
            print(f"{'='*40}")
            print(f"  Clientes: {stats['clients']['total']} (ativos: {stats['clients']['active']})")
            print(f"  Licenças: {stats['licenses']['total']}")
            print(f"    - Ativas: {stats['licenses']['active']}")
            print(f"    - Expiradas: {stats['licenses']['expired']}")
            print(f"    - Pendentes: {stats['licenses']['pending']}")
            print(f"    - Expirando em 30 dias: {stats['licenses']['expiring_soon']}")
            print(f"  Validações (24h): {stats['validations']['last_24h']}")
            print(f"{'='*40}")
        else:
            print(f"✗ Erro: {response.text}")
    except Exception as e:
        print(f"✗ Erro: {e}")


def print_help():
    print("""
License Server - CLI Admin
===========================

Comandos disponíveis:

  python admin_cli.py login                              - Fazer login
  python admin_cli.py stats                              - Ver estatísticas

  python admin_cli.py clients list                       - Listar clientes
  python admin_cli.py clients create "Nome" "email"      - Criar cliente

  python admin_cli.py licenses list                      - Listar licenças
  python admin_cli.py licenses create <client_id> [plano] [dias]
                                                         - Criar licença
                                                           Planos: starter, professional, enterprise, unlimited
                                                           Dias: padrão 365
  python admin_cli.py licenses revoke <chave>            - Revogar licença

Exemplos:
  python admin_cli.py clients create "Empresa ABC" "contato@abc.com"
  python admin_cli.py licenses create abc123-uuid professional 365
  python admin_cli.py licenses revoke XXXX-XXXX-XXXX-XXXX
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "login":
        cmd_login()
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "clients":
        if len(sys.argv) < 3:
            print("Uso: clients [list|create]")
        elif sys.argv[2] == "list":
            cmd_clients_list()
        elif sys.argv[2] == "create" and len(sys.argv) >= 5:
            cmd_clients_create(sys.argv[3], sys.argv[4])
        else:
            print("Uso: clients create 'Nome' 'email@empresa.com'")
    elif cmd == "licenses":
        if len(sys.argv) < 3:
            print("Uso: licenses [list|create|revoke]")
        elif sys.argv[2] == "list":
            cmd_licenses_list()
        elif sys.argv[2] == "create" and len(sys.argv) >= 4:
            plan = sys.argv[4] if len(sys.argv) > 4 else "professional"
            days = sys.argv[5] if len(sys.argv) > 5 else "365"
            cmd_licenses_create(sys.argv[3], plan, days)
        elif sys.argv[2] == "revoke" and len(sys.argv) >= 4:
            cmd_licenses_revoke(sys.argv[3])
        else:
            print("Uso: licenses create <client_id> [plano] [dias]")
    elif cmd == "help":
        print_help()
    else:
        print(f"Comando desconhecido: {cmd}")
        print_help()
