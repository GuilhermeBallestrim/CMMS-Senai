import urllib.request
import urllib.parse
import http.cookiejar
import re

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

BASE = 'http://127.0.0.1:8000'

def get(path):
    try:
        r = opener.open(BASE + path, timeout=10)
        body = r.read().decode('utf-8', errors='replace')
        return r.status, body, dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return e.code, body, dict(e.headers)
    except Exception as e:
        return None, f"EXCECAO: {type(e).__name__}: {e}", {}

def post(path, data_dict):
    data = urllib.parse.urlencode(data_dict).encode()
    req = urllib.request.Request(BASE + path, data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        r = opener.open(req, timeout=10)
        body = r.read().decode('utf-8', errors='replace')
        return r.status, body, dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return e.code, body, dict(e.headers)
    except Exception as e:
        return None, f"EXCECAO: {type(e).__name__}: {e}", {}

print("=" * 60)
print("TESTE: Login com teste@teste.com")
print("=" * 60)
status, body, headers = get('/login')
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]*)"', body)
print(f"GET /login: Status {status}, CSRF: {'OK' if csrf_match else 'FALHA'}")

if csrf_match:
    status, body, headers = post('/login', {
        'email': 'teste@teste.com',
        'password': 'Teste12345678',
        'csrf_token': csrf_match.group(1),
    })
    print(f"POST /login: Status {status}")
    if status == 303:
        print(f"  SUCESSO! Redirecionou para: {headers.get('Location', 'N/A')}")
    elif status == 200:
        print(f"  Login falhou (senha incorreta)")
    elif status == 500:
        print(f"  ERRO 500: {body[:500]}")

print("\n" + "=" * 60)
print("TESTE: GET /equipamentos (logado)")
print("=" * 60)
status, body, headers = get('/equipamentos')
print(f"GET /equipamentos: Status {status}")
if status == 500:
    print(f"  ERRO 500: {body[:800]}")
elif status == 200:
    if 'Fresa 02' in body:
        print("  Equipamento 'Fresa 02' encontrado no HTML - SUCESSO!")
    if 'Nenhum equipamento' in body:
        print("  Mensagem 'Nenhum equipamento cadastrado'")
    if 'Equipamentos' in body:
        print("  Título 'Equipamentos' encontrado")

print("\n" + "=" * 60)
print("TESTE: GET /chamados/novo (logado)")
print("=" * 60)
status, body, headers = get('/chamados/novo')
print(f"GET /chamados/novo: Status {status}")
if status == 500:
    print(f"  ERRO 500: {body[:800]}")
elif status == 200:
    csrf_match2 = re.search(r'name="csrf_token"[^>]*value="([^"]*)"', body)
    equipamentos = re.findall(r'<option value="(\d+)">([^<]+)</option>', body)
    print(f"CSRF: {'OK' if csrf_match2 else 'FALHA'}")
    print(f"Equipamentos no select: {len(equipamentos)}")
    for e in equipamentos:
        print(f"  - {e[1]} (id={e[0]})")

print("\n" + "=" * 60)
print("TESTE: POST /chamados (logado)")
print("=" * 60)
status, body, headers = get('/chamados/novo')
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]*)"', body)
equipamentos = re.findall(r'<option value="(\d+)">([^<]+)</option>', body)

if csrf_match and equipamentos:
    equip_id = equipamentos[0][0]
    print(f"Criando chamado com equipamento id={equip_id}...")
    status, body, headers = post('/chamados', {
        'equipment_id': equip_id,
        'description': 'Teste de chamado para verificar erro 500',
        'priority': 'Média',
        'problem_type': 'Inspeção/troca das correias da fresa',
        'problem_other': '',
        'noise_vibration': 'false',
        'overheating': 'false',
        'other_symptoms': '',
        'csrf_token': csrf_match.group(1),
    })
    print(f"POST /chamados: Status {status}")
    if status == 500:
        print(f"  ERRO 500: {body[:800]}")
    elif status == 303:
        print(f"  SUCESSO! Redirecionou para: {headers.get('Location', 'N/A')}")
    else:
        print(f"  Status: {status}")
        print(f"  Body: {body[:200]}")
elif not equipamentos:
    print("  Nenhum equipamento - não consigo testar POST")

print("\n" + "=" * 60)
print("TESTE: GET /dashboard (logado)")
print("=" * 60)
status, body, headers = get('/dashboard')
print(f"GET /dashboard: Status {status}")
if status == 500:
    print(f"  ERRO 500: {body[:800]}")
elif status == 200:
    print("  Dashboard carregado com sucesso")
