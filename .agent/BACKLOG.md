# Backlog — Spider-Nix

> Auto-discovered issues and improvement opportunities.
> Format: Type | Severity | Status | Found while | Location

---

## GUI Upgrade — Desktop-Class Experience

- Type: feature
- Severity: high
- Status: open
- Found while: Full project analysis
- Location: `src/spider_nix/server/`, `docs/GUI_DESIGN.md`
- Description:
  O GUI atual é FastAPI + Alpine.js + HTMX + Tailwind CDN. Funcional, mas limitado:
  - Tailwind via CDN = sem purge, bundle pesado
  - HTMX troca HTML parcial, sem state management real
  - Sem hot reload no dev
  - Visual "genérico" sem identidade própria (Tailwind default)
  - Navegação por page reload (SPA-like só via HTMX swaps)
  - Sem offline support
- Why it matters:
  O GUI é a cara do produto. O backend é forte, mas o frontend atual passa
  impressão de ferramenta interna, não de produto polido. O próprio `docs/GUI_DESIGN.md`
  descreve uma experiência muito mais rica do que a implementada.
- Suggested next step:
  Migrar para React + Vite + Tailwind (buildado) ou Tauri para desktop app.
  Ver seção "Why Not Electron/Tauri" no GUI_DESIGN.md — a justificativa é válida
  mas um app desktop Tauri seria um diferencial enorme.

---

## CLI Monolith — Refactor to Command Modules

- Type: refactor
- Severity: high
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/cli.py` (~2600 lines, 72 symbols)
- Description:
  `cli.py` é um arquivo monolítico com todos os comandos CLI (crawl, recon, web, job, wizard, etc).
  Typer suporta `add_typer()` para composição de subcommands.
- Why it matters:
  Manutenção difícil, diffs gigantes, impossível testar comandos isoladamente,
  risco alto de conflitos de merge.
- Suggested next step:
  Extrair para `cli/` package:
  - `cli/jobs.py` — `spider job *`
  - `cli/recon.py` — `spider recon *`
  - `cli/web.py` — `spider web *`
  - `cli/crawl.py` — `spider crawl`
  - `cli/dev.py` — `spider test/lint/fmt/ci-local`

---

## Test Suite Health — Green?

- Type: test
- Severity: critical
- Status: open
- Found while: Full project analysis
- Location: `tests/` (14 test files)
- Description:
  Não foi possível rodar a suíte de testes no ambiente atual. `pytest` não
  disponível no PATH e `nix develop` demorou. CI workflows existem mas não
  sabemos o último status.
- Why it matters:
  Sem testes passando, qualquer mudança é arriscada. Precisamos confirmar
  que a suíte está verde antes de refatorar ou adicionar features.
- Suggested next step:
  Rodar `nix develop --command spider test` (ou `uv run pytest`) e verificar
  status. Corrigir falhas se existirem.

---

## Missing API Endpoints in Web GUI

- Type: feature
- Severity: medium
- Status: open
- Found while: Comparing GUI_DESIGN.md with server/__init__.py
- Location: `src/spider_nix/server/__init__.py`
- Description:
  O `docs/GUI_DESIGN.md` lista 14 endpoints REST + WebSocket. A implementação
  atual tem apenas ~10. Faltam:
  - `GET /api/jobs/{job_id}` — job detail
  - `POST /api/jobs/{job_id}/apply` — mark applied
  - `POST /api/jobs/{job_id}/notes` — add notes
  - `POST /api/autofill/execute` — live fill via browser
  - `POST /api/profile/resume` — upload and parse resume
- Why it matters:
  Features documentadas mas não acessíveis via GUI. Pipeline e Auto-fill
  incompletos na interface web.
- Suggested next step:
  Implementar os endpoints faltantes, priorizando `/api/autofill/execute`
  e `/api/profile/resume`.

---

## WebSocket Live Hunt — Inefficient Polling

- Type: performance
- Severity: medium
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/server/__init__.py` L266-287
- Description:
  O WebSocket `/ws/live` faz polling a cada 1 segundo por 60 segundos
  (`for _ in range(60): await asyncio.sleep(1)`). Não usa eventos assíncronos
  reais — é polling disfarçado de WebSocket.
- Why it matters:
  Latência de até 1s nas atualizações, desperdício de CPU. O backend já
  usa `asyncio.Queue` — poderia usar `asyncio.Event` ou pub/sub real.
- Suggested next step:
  Refatorar para pattern pub/sub com `asyncio.Event` onde o hunt job notifica
  o WebSocket handler diretamente em vez de polling.

---

## Hardcoded Currency Exchange Rates

- Type: bug
- Severity: low
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/intel/job_matcher.py` L362
- Description:
  Taxas de câmbio hardcoded no `_score_salary()`:
  ```python
  rates = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "BRL": 0.19, "CAD": 0.73}
  ```
  Comentário no código: `# TODO: use an API`
- Why it matters:
  Scores de salary imprecisos para moedas não-USD. Baixo impacto imediato
  mas vai deteriorando conformo taxas mudam.
- Suggested next step:
  Usar `forex-python` ou API gratuita (exchangerate-api.com) com cache de 1h.

---

## Go Proxy Binary in Repo

- Type: security
- Severity: medium
- Status: open
- Found while: Code analysis
- Location: `network/spider-network-proxy` (binary file)
- Description:
  Binário compilado do Go proxy está commitado no repositório. Isso é:
  - Não reprodutível (não sabemos com qual source foi compilado)
  - Risco de supply chain (binário pode ser malicioso)
  - Incha o repo desnecessariamente
- Why it matters:
  Violação de Supply Chain Security. O AGENTS.md manda manter
  reprodutibilidade. O flake.nix já tem `packages.spider-network-proxy`
  que builda do source.
- Suggested next step:
  Remover binário do git (`git rm --cached`), adicionar ao `.gitignore`,
  buildar via `nix build .#spider-network-proxy` ou `just proxy-build`.

---

## No Web GUI Authentication

- Type: security
- Severity: medium
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/server/__init__.py`
- Description:
  O servidor FastAPI não tem nenhuma autenticação. Qualquer pessoa na
  rede local pode acessar `localhost:8000` e ver dados de pipeline,
  perfil, e disparar hunts.
- Why it matters:
  Dados de job search são sensíveis (salário, empresas alvo, status de
  candidatura). Em ambiente compartilhado, é um problema.
- Suggested next step:
  Adicionar autenticação básica (HTTP Basic Auth ou token simples) com
  flag `--no-auth` para dev. Documentar no README.

---

## Template Loader: Fallback YAML Parser Frágil

- Type: bug
- Severity: medium
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/intel/template_loader.py` L35-84
- Description:
  O `_parse_simple_yaml()` é um parser YAML manual que cobre apenas
  o formato específico dos templates atuais. Qualquer evolução nos
  templates (aninhamento, listas de dicionários, multi-linha) vai quebrar.
  O `pyyaml` já está nas dependências (`pyproject.toml`).
- Why it matters:
  Frágil, não escala, potencial de quebra silenciosa com templates
  ligeiramente diferentes. O fallback só é usado se `import yaml` falhar,
  mas `pyyaml` é dependência hard.
- Suggested next step:
  Remover o fallback parser. Assumir `pyyaml` sempre disponível. Simplificar
  `_load_yaml()` para usar só `yaml.safe_load()`.

---

## Missing `py.typed` Marker

- Type: dx
- Severity: low
- Status: open
- Found while: pyproject.toml analysis
- Location: `src/spider_nix/`
- Description:
  O projeto usa mypy e tem type hints mas não tem `py.typed` (PEP 561).
  Isso significa que IDEs e mypy de projetos dependentes não conseguem
  usar os tipos exportados.
- Why it matters:
  DX reduzido para quem importa spider-nix como lib. Baixo impacto imediato
  (é mais CLI tool que lib), mas fácil de resolver.
- Suggested next step:
  Adicionar arquivo vazio `src/spider_nix/py.typed` e garantir que
  `tool.hatch.build.targets.wheel` inclua ele.

---

## Unused `__pycache__` in Git

- Type: dx
- Severity: low
- Status: open
- Found while: Directory listing
- Location: `src/spider_nix/osint/__pycache__/`, `src/spider_nix/ml/__pycache__/`, `src/spider_nix/extraction/__pycache__/`
- Description:
  Diretórios `__pycache__` aparecem na listagem. O `.gitignore` pode não
  estar cobrindo todos os caminhos ou foram commitados antes do gitignore.
- Why it matters:
  Poluição no repo, diffs sujos. Baixo impacto mas trivial de limpar.
- Suggested next step:
  Verificar se `.gitignore` cobre `__pycache__/` recursivamente.
  Se sim, `git rm --cached -r` nos dirs. Se não, adicionar ao `.gitignore`.

---

## Resume Parser — Limited Skill Detection

- Type: feature
- Severity: medium
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/intel/resume_parser.py` L355-368
- Description:
  `extract_skills()` usa `TECH_KEYWORDS` do módulo `jobs.py` para detectar
  skills. São ~40 palavras-chave. Para um parser de currículo, isso é
  limitado — Kubernetes tem muitas sub-techs, cloud providers, databases, etc.
- Why it matters:
  Qualidade do auto-fill e job matching depende da qualidade da extração
  de skills do currículo. Sub-extração = scores baixos = matches ruins.
- Suggested next step:
  Expandir `TECH_KEYWORDS` com ~200+ termos do mercado (usar dados do
  StackOverflow survey ou GitHub linguist). Considerar embedding-based
  matching para termos não-listados.

---

## ATS Templates — Only 3 Platforms

- Type: feature
- Severity: medium
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/intel/templates/` (greenhouse.yaml, lever.yaml, ashby.yaml)
- Description:
  Templates YAML só cobrem Greenhouse, Lever, e Ashby. O README menciona
  Workday mas não tem template. Outras plataformas comuns: BambooHR,
  SmartRecruiters, JazzHR, BreezyHR.
- Why it matters:
  Auto-fill funciona bem só nessas 3 plataformas. Nas outras, cai no
  modo genérico (label matching) que é menos preciso.
- Suggested next step:
  Adicionar templates para Workday, BambooHR, SmartRecruiters. Criar
  script `scripts/scrape_field_names.py` que extrai nomes de campo
  automaticamente de aplicações reais.

---

## Server Templates — Inline Styles, No Components

- Type: refactor
- Severity: low
- Status: open
- Found while: Server template analysis
- Location: `src/spider_nix/server/templates/*.html`
- Description:
  Templates HTML usam Alpine.js + Tailwind CDN. Funciona mas:
  - Sem componentização (repetição de markup)
  - Tailwind CDN = sem JIT/purge, bundle ~3MB
  - HTMX + Alpine tem comportamento imprevisível em edge cases
- Why it matters:
  Se for mexer no GUI (que é prioridade alta), vale a pena já pensar
  em componentização. Mesmo mantendo server-side rendering, Jinja2
  macros/components ajudam.
- Suggested next step:
  Extrair componentes Jinja2 reutilizáveis (navbar, job-card, status-badge).
  Avaliar migração para React/Vue se o escopo crescer.

---

## `__init__.py` Files — Circular Import Risk

- Type: architecture
- Severity: low
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/intel/__init__.py`
- Description:
  O `__init__.py` do `intel` importa de todos os submódulos. Isso cria
  um acoplamento forte — importar qualquer coisa de `intel` carrega
  tudo (scrapers, storage, form_filler, resume_parser).
- Why it matters:
  Tempo de import aumentado, risco de circular imports, difícil de
  testar módulos isoladamente. Baixo impacto agora, mas vai piorar
  conforme novos módulos são adicionados.
- Suggested next step:
  Considerar lazy imports ou `__all__` sem import real. Ou manter
  como está (conveniência vs pureza) mas documentar o tradeoff.

---

## `SESSION_EXAMPLE` Function Exposed in Module

- Type: security
- Severity: low
- Status: open
- Found while: Code analysis
- Location: `src/spider_nix/session.py` L344-367
- Description:
  `session_example()` contém credenciais hardcoded:
  ```python
  credentials={"username": "user@example.com", "password": "password123"}
  ```
  E `if __name__ == "__main__": asyncio.run(session_example())`
  Não é uma vulnerabilidade real (são credenciais de exemplo), mas
  scanners de segurança (Bandit, Semgrep) vão flagar.
- Why it matters:
  Falso positivo em security scans. Código de exemplo em módulo de
  produção. Já tem `# nosec B105` — pode ser suficiente.
- Suggested next step:
  Mover exemplo para `examples/session_example.py` e remover
  `if __name__ == "__main__"` do módulo principal.
