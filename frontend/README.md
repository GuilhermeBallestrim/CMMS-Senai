# SENAI CMMS — Front-end do protótipo

Protótipo visual desktop-first preparado para integração posterior com FastAPI e uma template engine compatível com Jinja.

## Estrutura

- `templates/base.html`: navegação, cabeçalho e recursos compartilhados.
- `templates/`: páginas organizadas por módulo e com herança Jinja.
- `static/css/`: estilos separados em base, layout, componentes e responsividade.
- `static/js/app.js`: interações somente visuais, sem chamadas a APIs.

## Páginas previstas

`/login`, `/dashboard`, `/chamados`, `/chamados/novo`, `/chamados/detalhe`, `/equipamentos`, `/equipamentos/novo`, `/equipamentos/detalhe`, `/ordens-servico`, `/ordens-servico/detalhe`, `/historico`, `/solicitacoes`, `/solicitacoes/nova`, `/solicitacoes/detalhe`, `/indicadores`, `/notificacoes` e `/configuracoes`.

Os formulários usam `action`, `method`, `name`, `id` e rótulos preparados para endpoints reais. Os valores de demonstração estão concentrados nos templates e devem ser substituídos por variáveis/contextos do backend. Não há servidor, rotas FastAPI, APIs ou regras de negócio implementadas nesta etapa.

Os estilos não dependem de framework CSS/JS. As classes seguem o padrão BEM; os tokens globais ficam em `static/css/base.css`.
