# Spider-Nix Job Hunt Automation — Roadmap

**Objetivo:** Agente autônomo que encontra, avalia, aplica e acompanha vagas remotas de
Security Architect / Platform Engineer com mínima intervenção humana.

**Estado atual:** MVP funcional com discovery multi-fonte, tracker SQLite, TUI de aprovação,
email monitor e scheduler daemon.

---

## O que está funcionando hoje

| Componente | Estado | Qualidade |
|---|---|---|
| Profile loader (TOML) | ✅ | Boa |
| ATS detectors (Greenhouse/Lever/Ashby/Workday) | ✅ | Boa |
| API-first submission | ✅ | Boa |
| SQLite tracker | ✅ | Boa |
| TUI approval gate + ntfy | ✅ | Boa |
| Discovery: RemoteOK, WWR, Jobicy, HN, company boards | ✅ | Média |
| IMAP email monitor + classificação regex | ✅ | Média |
| Asyncio scheduler daemon | ✅ | Média |
| Personal scorer | ✅ | Fraca |
| Stealth nos requests de discovery | ❌ | Não existe |
| Cover letter personalizada por vaga | ❌ | Não existe |
| Deduplicação robusta | ❌ | Só por URL |
| LinkedIn/Indeed scraping | ❌ | Não existe |
| Analytics e relatórios | ❌ | Não existe |

---

## Fase 1 — Qualidade do core (agora)

O que torna o produto ruim hoje não é falta de features, é que as features existentes
entregam resultados ruins. Isso precisa ser resolvido antes de adicionar qualquer coisa nova.

### 1.1 Scorer inteligente
**Problema:** React dev com score 41 passa o threshold de 40. O scorer atual soma pontos
por skills presentes mas não penaliza quando o título é completamente fora do target.

**Solução:**
- Penalidade forte (-40) se título não tiver match com nenhum `target_roles`
- Peso maior para match de título (25pts) vs skill isolada (8pts)
- Bonus por stack completa (Security + Rust + NixOS juntos = 20pts extra)
- Penalidade por sinais de nível errado ("junior", "intern", "entry-level")
- Threshold mínimo real: 55 com título obrigatório ter algum match

```
intel/personal_scorer.py — reescrever lógica de pontuação
```

### 1.2 Stealth nos requests de discovery
**Problema:** Todo fetch vai com `User-Agent: Mozilla/5.0` hardcoded. RemoteOK e WWR
já detectam isso.

**Solução:** Integrar `StealthEngine` (já existe em `stealth.py`) no `JobDiscovery`:
- Headers aleatórios por request (`StealthEngine.get_headers()`)
- Jitter entre 1–4s entre calls de sources diferentes
- User-Agent rotacionado a cada request
- Accept headers diferenciados por tipo de fonte (JSON vs RSS vs HTML)

```
intel/job_discovery.py — adicionar _stealth_client() helper
```

### 1.3 Deduplicação robusta
**Problema:** Mesmo job postado em RemoteOK e WWR entra duas vezes. Dedup atual é
só por URL exata.

**Solução:**
- Normalizar URL antes de comparar (strip UTM params, trailing slash, www)
- Hash secundário: `company_slug + title_slug` — se bate, é duplicata
- Fuzzy match no título (ratio > 0.85) dentro da mesma empresa

```
intel/job_discovery.py — _normalize_url() + _is_duplicate()
```

### 1.4 Fonte: Greenhouse search direto
**Problema:** Hoje só poleia boards de empresas hardcoded no `profile.toml`. Mas qualquer
empresa que usa Greenhouse tem board público em `boards.greenhouse.io`.

**Solução:** Query na Greenhouse search API com keywords do perfil — retorna dezenas de
empresas não listadas que usam o mesmo ATS.

```python
# GET https://boards-api.greenhouse.io/v1/boards?for=security+architect
intel/job_discovery.py — _fetch_greenhouse_search()
```

### 1.5 Cover letter personalizada por vaga
**Problema:** Cover letter atual é o template do `profile.toml` enviado igual pra todas
as vagas. Isso é detectável e impessoal.

**Solução:** LLM local (Ollama/Mistral já configurado no perfil) gera cover letter
específica por vaga usando:
- Título e empresa da vaga
- Stack mencionada na descrição
- Contexto do perfil (`profile.as_context_string()`)
- Template base do `profile.toml` como guia de tom

```
intel/cover_letter.py — novo módulo
intel/llm_mapper.py — reaproveitar client LLM
```

---

## Fase 2 — Mais fontes, mais sinal

Com o core funcionando bem, expandir as origens de vagas.

### 2.1 LinkedIn Jobs scraping (headless)
O maior board de vagas do mundo. Não tem API pública.

**Estratégia:**
- Playwright headless com `StealthEngine` + fingerprint completo
- Login com cookie session salvo (não precisa logar toda vez)
- Search: `site:linkedin.com/jobs "security architect" OR "platform engineer" remote`
- Rate limit agressivo: máx 30 jobs por ciclo, delay 3–8s entre pages
- Respeitar detecção: se CAPTCHA → pausar source por 24h, notificar via ntfy

```
intel/sources/linkedin.py — novo módulo
intel/job_discovery.py — integrar como source opcional
profile.toml — [linkedin] session_cookie = "..."
```

### 2.2 Indeed RSS
Indeed tem feeds RSS públicos por query que não requerem auth.

```
https://www.indeed.com/rss?q=security+architect&l=remote&jt=fulltime
intel/sources/indeed_rss.py
```

### 2.3 Ashby search global
Ashby tem um endpoint de busca cross-company semelhante ao Greenhouse.

```
intel/sources/ashby_search.py
```

### 2.4 Wellfound (AngelList) — startups tech
Muito usado por empresas de infra/security remote-first. API parcialmente pública.

```
intel/sources/wellfound.py
```

### 2.5 Remotive API
Similar ao RemoteOK mas com melhor categorização por área.

```
https://remotive.com/api/remote-jobs?category=devops-sysadmin
intel/sources/remotive.py
```

---

## Fase 3 — Automação de relacionamento

### 3.1 Follow-up automático por email
**Lógica:**
- Após 7 dias sem resposta → enviar follow-up educado
- Template configurável no `profile.toml`
- Só executa se `email.send_followups = true` no perfil
- Registra o follow-up no tracker (evento no `events` table)

```
intel/followup.py — novo módulo
intel/scheduler.py — adicionar _followup_loop()
```

### 3.2 Ghosting detector
Vaga com status `submitted` há mais de 21 dias sem nenhum email → marca como `ghosted`
automaticamente e envia notificação ntfy.

```
intel/scheduler.py — _ghosting_check() no loop diário
```

### 3.3 Interview tracker
Quando email classificado como `interview_invite`:
- Extrai data/hora via regex + LLM fallback
- Cria evento na tabela `events`
- Opcionalmente cria evento no Google Calendar via API

```
intel/interview_tracker.py
```

---

## Fase 4 — Inteligência e feedback loop

### 4.1 Scorer com histórico
O scorer atual é estático. Com dados reais no tracker, ele pode aprender:
- Quais scores correlacionam com entrevistas reais
- Quais empresas respondem mais
- Quais keywords no título são indicativas de nível sênior

**Implementação:** usar `ml/feedback_logger.py` (já existe) para registrar score vs outcome
e ajustar pesos do scorer ao longo do tempo.

```
intel/personal_scorer.py — modo adaptativo
ml/feedback_logger.py — já existe, integrar
```

### 4.2 Análise de rejeições
Quando email é classificado como `rejection`, LLM analisa o body para extrair:
- Motivo provável (experiência, localização, salário, timing)
- Pattern: se 3+ rejeições da mesma empresa → blacklist temporária

```
intel/email_monitor.py — _analyze_rejection()
```

### 4.3 Salary intelligence
Antes de submeter, consultar:
- Levels.fyi API (existe, não requer auth) para benchmark de salário por empresa/nível
- Comparar com `min_salary_usd` do perfil
- Mostrar no TUI de aprovação: "Cloudflare P4 mediana: $185k"

```
intel/salary_intel.py — novo módulo
intel/approval_gate.py — integrar no display
```

### 4.4 Batch apply com fila prioritária
Hoje o `job-hunt` daemon aplica na ordem de chegada. Com dados históricos:
- Priorizar empresas com maior taxa de resposta
- Priorizar vagas com salary listado
- Aplicar em horário comercial do timezone da empresa (melhora taxa de leitura)

```
intel/scheduler.py — _apply_queued() com priorização
```

---

## Fase 5 — Interface e observabilidade

### 5.1 Dashboard TUI completo
`spider job-status` hoje mostra só contagem. Deveria mostrar:
- Funil visual: queued → submitted → interview → offer
- Timeline de atividade últimos 30 dias
- Taxa de resposta por empresa/fonte
- Vagas próximas de ghosting (submited > 14d)

```
cli.py — job-status expandido com Rich layout + panels
```

### 5.2 Relatório semanal
Todo domingo, email/ntfy com:
- Novas vagas encontradas na semana
- Status de cada aplicação ativa
- Entrevistas agendadas
- Sugestão de follow-ups pendentes

```
intel/weekly_report.py
intel/scheduler.py — loop semanal
```

### 5.3 Export
```
spider job-export --format csv|json|pdf
```
Para enviar pro recrutador ou ter backup das aplicações.

---

## Débito técnico a resolver em paralelo

| Item | Impacto | Esforço |
|---|---|---|
| `tracker.py` sem FTS5 — busca por texto é lenta | Médio | Baixo |
| `record_application` silencia erros de duplicata — logs | Baixo | Baixo |
| `email_monitor.py` usa IMAP polling — considerar push (Gmail API) | Médio | Alto |
| Nenhum retry com backoff nos fetches de discovery | Médio | Baixo |
| `applications.db` path hardcoded — deveria ser XDG_DATA_HOME | Baixo | Baixo |
| Sem migration system no schema SQLite | Médio | Médio |
| `stealth.py` depende de `fake_useragent` que faz request na internet — cachear | Baixo | Baixo |

---

## Fase 6 — Integração com O.W.A.S.A.K.A

O.W.A.S.A.K.A (`~/master/owasaka`) é um SIEM air-gapped em Go com módulos que complementam
diretamente o que spider-nix precisa para ser mais resiliente e expandir para LinkedIn.

**O que vale integrar:**

### 6.1 Proxy MITM como detector de bloqueio
O módulo `internal/network/proxy/` do owasaka intercepta TLS e faz Deep Packet Inspection.
Spider-nix roteia os requests de discovery por ele. Quando uma fonte retorna 429/403/CAPTCHA,
owasaka detecta e notifica via WebSocket — spider-nix pausa aquela source automaticamente.

Hoje: Jobicy retorna 400 e o erro é silenciado com `logger.warning`. Sem visibilidade de
quanto tempo ficou bloqueado ou se voltou.

```
intel/job_discovery.py  — _stealth_client() checa owasaka antes de cada fetch
intel/scheduler.py      — _source_health: dict[str, bool] pausado por owasaka events
profile.toml            — [owasaka] proxy_url = "http://localhost:8080"
```

### 6.2 Firefox/CDP para LinkedIn (Fase 2.1 via owasaka)
Owasaka tem `internal/browser/automation/` — Firefox hardened com políticas de segurança
e um CDP client completo. Em vez de spider-nix gerenciar um browser próprio para LinkedIn,
ele delega para owasaka que já tem o browser configurado com stealth.

```
intel/sources/linkedin.py  — CDP client conecta em owasaka:9222
owasaka já gerencia       — user-agent rotation, cookie isolation, TLS fingerprint
```

### 6.3 NATS event bus (opcional)
Quando owasaka está no ar, spider-nix publica eventos de job no mesmo bus NATS:

| Evento | Payload |
|---|---|
| `job.found.v1` | company, title, url, score |
| `job.applied.v1` | company, role, ats_platform |
| `job.interview.v1` | company, scheduled_at |
| `job.offer.v1` | company, salary |

Abre correlações futuras dentro do owasaka — ex: identificar padrões de rede ou
agrupar eventos de recrutamento por empresa.

```
intel/event_publisher.py  — nats client opcional (publica só se owasaka está up)
```

**O que não vale integrar:**
- Asset discovery, ARP scan, port scan — contexto completamente diferente
- BoltDB do owasaka — tracker SQLite já funciona
- ML anomaly detection do owasaka — precisa ser treinado com contexto de job hunting

**Pré-requisito:** owasaka rodando localmente. Integração é 100% opcional — se owasaka
não estiver up, spider-nix funciona normalmente sem ele.

---

## Ordem de execução recomendada

```
Fase 1.1 → 1.2 → 1.3   (scorer + stealth + dedup — máximo impacto, mínimo esforço)
Fase 1.4 → 1.5          (mais fonte + cover letter personalizada)
Fase 2.2 → 2.5          (fontes fáceis: Indeed RSS, Remotive)
Débito técnico          (retry + FTS5 + XDG paths)
Fase 3.1 → 3.2          (follow-up + ghosting)
Fase 6.1                (owasaka proxy — detector de bloqueio)
Fase 2.1 via 6.2        (LinkedIn usando Firefox do owasaka)
Fase 4.1 → 4.3          (inteligência — requer dados históricos acumulados)
Fase 5                  (dashboard + relatórios — qualidade de vida)
Fase 6.3                (NATS — quando owasaka estiver em produção)
```

---

## Métricas de sucesso

| Métrica | Hoje | Meta |
|---|---|---|
| Taxa de match relevante (vagas na fila que seriam aplicadas) | ~10% | >60% |
| Fontes funcionando por ciclo | 4/5 | 6/7 |
| Tempo médio da descoberta à aplicação | manual | <30min com TUI |
| Cobertura de email monitor | básica | rejections + interviews + offers |
| Entrevistas geradas por mês | 0 (novo) | 3–5 |

---

*Gerado em 2026-05-02 — atualizar conforme implementação avança*
