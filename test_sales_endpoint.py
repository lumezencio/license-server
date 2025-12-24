import requests
import json

# Pega token do localStorage (você precisa copiar do navegador)
print("TESTE DO ENDPOINT GET /gateway/sales")
print("=" * 60)
print()
print("⚠️  ATENÇÃO: Este teste requer um token válido!")
print()
print("1. Abra o navegador em http://localhost:5173")
print("2. Abra o DevTools (F12) → Console")
print("3. Digite: localStorage.getItem('access_token')")
print("4. Copie o token (sem aspas)")
print()
token = input("Cole o token aqui: ").strip()

if not token:
    print("❌ Token não fornecido!")
    exit(1)

# Faz requisição
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("\n🔄 Testando GET http://localhost:8080/api/gateway/sales")
print()

try:
    response = requests.get(
        "http://localhost:8080/api/gateway/sales",
        headers=headers,
        timeout=10
    )
    
    print(f"Status Code: {response.status_code}")
    print()
    
    if response.status_code == 200:
        data = response.json()
        
        if isinstance(data, list):
            print(f"✅ Retornou {len(data)} vendas")
            
            if len(data) > 0:
                print()
                print("🔍 PRIMEIRA VENDA:")
                print("-" * 60)
                first_sale = data[0]
                print(f"ID: {first_sale.get('id')}")
                print(f"Número: {first_sale.get('sale_number')}")
                print(f"Cliente: {first_sale.get('customer_name')}")
                print(f"Total: R$ {first_sale.get('total_amount', 0)}")
                print()
                
                # VERIFICA SE TEM ITEMS (O PONTO CRÍTICO!)
                items = first_sale.get('items', [])
                print(f"🎯 ITEMS: {len(items)} itens encontrados")
                
                if items:
                    print()
                    print("✅✅✅ SUCESSO! Backend está retornando items!")
                    print()
                    for idx, item in enumerate(items, 1):
                        print(f"  Item {idx}: {item.get('product_name', 'N/A')} - Qtd: {item.get('quantity', 0)}")
                else:
                    print()
                    print("❌❌❌ ERRO! Items NÃO estão sendo retornados!")
                    print()
                    print("Estrutura da venda:")
                    print(json.dumps(first_sale, indent=2, ensure_ascii=False))
        else:
            print("Resposta inesperada:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"❌ Erro HTTP {response.status_code}")
        print(response.text)
        
except Exception as e:
    print(f"❌ Erro: {str(e)}")
