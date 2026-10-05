"""SENAI CMMS prototype web app.

This application serves the Jinja interface and accepts prototype form posts.
It deliberately does not persist data or implement authentication/business rules.
"""

from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"

app = FastAPI(title="SENAI CMMS", description="Protótipo visual do sistema de manutenção")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")


def render(request: Request, template: str, *, notice: str | None = None):
    """Render a page using the shared template context."""
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"notice": notice or request.query_params.get("notice", "")},
    )


def redirect_with_notice(path: str, message: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?{urlencode({'notice': message})}", status_code=303)


async def accept_demo_form(request: Request, message: str, destination: str) -> RedirectResponse:
    """Consume submitted fields and return a visible prototype confirmation.

    Form values and uploaded files are intentionally not saved. This provides a
    working browser flow while the database and business rules are still pending.
    """
    await request.form()
    return redirect_with_notice(destination, message)


@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse("/login", status_code=303)


@app.get("/login", name="login")
async def login_page(request: Request):
    return render(request, "login.html")


@app.post("/login", name="login_submit")
async def login_submit(request: Request):
    # Demo-only: this confirms the visual flow; it does not authenticate anyone.
    return await accept_demo_form(request, "Acesso de demonstração iniciado.", "/dashboard")


@app.get("/recuperar-senha", include_in_schema=False)
async def password_recovery(request: Request):
    return render(request, "login.html", notice="Recuperação de senha será conectada ao backend de autenticação.")


@app.get("/dashboard", name="dashboard")
async def dashboard(request: Request):
    return render(request, "dashboard.html")


@app.get("/chamados", name="chamados")
async def chamados(request: Request):
    return render(request, "chamados/lista.html")


@app.get("/chamados/novo", name="novo_chamado")
async def novo_chamado(request: Request):
    return render(request, "chamados/novo.html")


@app.post("/chamados", name="criar_chamado")
async def criar_chamado(request: Request):
    return await accept_demo_form(request, "Chamado recebido neste protótipo.", "/chamados")


@app.get("/chamados/detalhe", name="detalhe_chamado")
async def detalhe_chamado(request: Request):
    return render(request, "chamados/detalhe.html")


@app.get("/equipamentos", name="equipamentos")
async def equipamentos(request: Request):
    return render(request, "equipamentos/lista.html")


@app.get("/equipamentos/novo", name="novo_equipamento")
async def novo_equipamento(request: Request):
    return render(request, "equipamentos/novo.html")


@app.post("/equipamentos", name="criar_equipamento")
async def criar_equipamento(request: Request):
    return await accept_demo_form(request, "Equipamento recebido neste protótipo.", "/equipamentos")


@app.get("/equipamentos/detalhe", name="detalhe_equipamento")
async def detalhe_equipamento(request: Request):
    return render(request, "equipamentos/detalhe.html")


@app.get("/ordens-servico", name="ordens_servico")
async def ordens_servico(request: Request):
    return render(request, "ordens_servico/lista.html")


@app.get("/ordens-servico/detalhe", name="detalhe_ordem_servico")
async def detalhe_ordem_servico(request: Request):
    return render(request, "ordens_servico/detalhe.html")


@app.post("/ordens-servico/OS-2025-056", name="atualizar_ordem_servico")
async def atualizar_ordem_servico(request: Request):
    return await accept_demo_form(request, "Atualização da OS recebida neste protótipo.", "/ordens-servico/detalhe")


@app.get("/historico", name="historico")
async def historico(request: Request):
    return render(request, "historico/lista.html")


@app.get("/solicitacoes", name="solicitacoes")
async def solicitacoes(request: Request):
    return render(request, "solicitacoes/lista.html")


@app.get("/solicitacoes/nova", name="nova_solicitacao")
async def nova_solicitacao(request: Request):
    return render(request, "solicitacoes/nova.html")


@app.post("/solicitacoes", name="criar_solicitacao")
async def criar_solicitacao(request: Request):
    return await accept_demo_form(request, "Solicitação recebida neste protótipo.", "/solicitacoes")


@app.get("/solicitacoes/detalhe", name="detalhe_solicitacao")
async def detalhe_solicitacao(request: Request):
    return render(request, "solicitacoes/detalhe.html")


@app.get("/indicadores", name="indicadores")
async def indicadores(request: Request):
    return render(request, "indicadores/lista.html")


@app.get("/notificacoes", name="notificacoes")
async def notificacoes(request: Request):
    return render(request, "notificacoes/lista.html")


@app.get("/configuracoes", name="configuracoes")
async def configuracoes(request: Request):
    return render(request, "configuracoes/lista.html")
