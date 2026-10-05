# SENAI CMMS

Protótipo web do sistema de gestão de manutenção industrial. A interface usa Jinja2 e CSS/JavaScript sem frameworks; a aplicação FastAPI serve as páginas e recebe os formulários de demonstração.

## Rodar no Windows

Abra o PowerShell nesta pasta do projeto e execute:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Depois, abra [http://127.0.0.1:8000](http://127.0.0.1:8000). O endereço `/` abre a tela de login; o envio do formulário de acesso leva ao dashboard.

Se o PowerShell bloquear a ativação do ambiente virtual, use o executável diretamente:

```powershell
\.venv\Scripts\python.exe -m pip install -r requirements.txt
\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

## Escopo atual

Este backend inicial serve todos os templates, arquivos estáticos e recebe os formulários do protótipo com uma mensagem de confirmação. **Ele não autentica usuários, não grava formulários ou arquivos, não usa banco de dados e não implementa regras de manutenção.** Os dados exibidos ainda são exemplos dos templates. Essas partes precisam ser conectadas em etapas posteriores.

Mais detalhes da organização do front-end estão em [frontend/README.md](frontend/README.md).
