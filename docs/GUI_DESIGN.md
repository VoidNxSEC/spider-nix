# GUI Design — Spider-Nix Frontend

> **Status: IMPLEMENTED** — FastAPI + Alpine.js + Tailwind CSS
> Launch with: `spider serve`

## Overview

A web-based GUI that exposes the full spider-nix pipeline through a clean dashboard.
Backend serves a REST API + WebSocket for live updates. Frontend is a single-page app.

```
┌──────────────────────────────────────────────────────────┐
│                   Browser (localhost:8000)                │
│                                                          │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐   │
│  │  🔍 Job │ │  📊 Pipe │ │  🤖 Auto │ │  ⚙️ Profile │   │
│  │  Hunt   │ │  Tracker │ │   Fill   │ │            │   │
│  └─────────┘ └──────────┘ └──────────┘ └────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │                                                  │    │
│  │              Main Content Area                   │    │
│  │     (dynamic, changes with selected tab)          │    │
│  │                                                  │    │
│  └──────────────────────────────────────────────────┘    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│            FASTAPI BACKEND (localhost:8000/api)           │
│                                                          │
│  /api/jobs/hunt     → POST  (trigger hunt)               │
│  /api/jobs/list     → GET   (list results with filters)  │
│  /api/jobs/apply    → POST  (mark as applied)            │
│  /api/pipeline      → GET   (funnel stats)               │
│  /api/autofill      → POST  (analyze form)               │
│  /api/profile       → GET/PUT (manage profile)           │
│  /ws/live           → WebSocket (live crawl progress)    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                SQLite DB (vagas.db)                       │
│  jobs │ applications │ profile │ templates               │
└──────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | **FastAPI** | Async, Pydantic nativo, WebSocket, auto OpenAPI docs |
| Frontend | **HTMX + Alpine.js** | Sem build step, leve, reativo o suficiente |
| CSS | **Tailwind CSS** (via CDN) | Rápido, utilitário, não precisa de bundler |
| Templates | **Jinja2** (FastAPI built-in) | Server-side rendering inicial |
| DB | **SQLite + aiosqlite** | Já temos, zero config |
| Real-time | **WebSocket** (FastAPI native) | Progresso do crawl ao vivo |

**Por que não React/Vue?** Pra um painel de controle interno, HTMX é suficiente e muito mais simples. Zero transpilação, zero node_modules.

---

## Pages

### 1. Job Hunt (`/`)
```
┌─────────────────────────────────────────────────────────┐
│  🔍 Job Hunt                                            │
│                                                         │
│  Skills:  [python, rust, nix, kubernetes    ] [Search]  │
│  ┌─────────────────────────────────────────────────────┐│
│  │ ☑ RemoteOK   ☑ WeWorkRemotely   ☑ HN Hiring       ││
│  │ ☑ Greenhouse ☑ Lever             ☑ Ashby          ││
│  │ Company: [stripe.com (optional)            ]        ││
│  │ Remote: [remote_preferred ▼]  Min Salary: [120000] ││
│  │ Max Jobs: [200]                                     ││
│  │                              [🚀 Start Hunt]        ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  Progress: ████████████░░░░░░░░ 58% (116/200)          │
│  Live log:                                              │
│  ✓ Greenhouse: 34 jobs                                   │
│  ✓ Lever: 12 jobs                                        │
│  ⏳ RemoteOK: fetching...                                │
│                                                         │
│  Results (scored):                        [Export JSON] │
│  ┌────┬───────┬──────────────────┬─────────┬──────────┐│
│  │ ⭐  │ Score │ Title            │ Company │ Source   ││
│  ├────┼───────┼──────────────────┼─────────┼──────────┤│
│  │ 📤 │ 95    │ Staff Platform.. │ Stripe  │ greenhouse││
│  │ 💾 │ 88    │ Senior SRE       │ AirBnB  │ lever     ││
│  │ 💾 │ 82    │ Backend Eng      │ DuckD.. │ hn_hiring ││
│  └────┴───────┴──────────────────┴─────────┴──────────┘│
└─────────────────────────────────────────────────────────┘
```

### 2. Pipeline (`/pipeline`)
```
┌─────────────────────────────────────────────────────────┐
│  📊 Application Pipeline                                │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ 💾 180   │→│ 📤  25   │→│ 📞  8    │→ ...          │
│  │  Saved   │  │ Applied  │  │  Phone   │              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                         │
│  Filter: [All ▼]  Sort: [Score ▼]                      │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Status │ Title              │ Company │ Date       ││
│  ├─────────────────────────────────────────────────────┤│
│  │ 📞     │ Platform Engineer  │ Stripe  │ 2025-05-18 ││
│  │ 📤     │ Senior SRE         │ AirBnB  │ 2025-05-17 ││
│  │ 💾     │ Backend Engineer   │ DuckD.. │ 2025-05-16 ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  Quick Actions:  [Mark Applied] [Schedule Interview]    │
│                  [Add Notes...]   [Reject]              │
└─────────────────────────────────────────────────────────┘
```

### 3. Auto-Fill (`/autofill`)
```
┌─────────────────────────────────────────────────────────┐
│  🤖 Auto-Fill                                           │
│                                                         │
│  Paste a job application URL:                           │
│  [https://jobs.lever.co/stripe/abc123           ]       │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Form detected: Application (Lever)                  ││
│  │                                                     ││
│  │ ┌──────────────────────────────────────────────────┐││
│  │ │ Field           │ Value              │ Conf  │   │││
│  │ ├──────────────────────────────────────────────────┤││
│  │ │ Full Name       │ João Silva         │ 🟢 95%│   │││
│  │ │ Email           │ joao@email.com     │ 🟢 99%│   │││
│  │ │ Phone           │ +55 11 99999-9999  │ 🟢 90%│   │││
│  │ │ LinkedIn        │ linkedin.com/in/.. │ 🟢 95%│   │││
│  │ │ Resume Upload   │ curriculo.pdf ⚠️    │ 🟡 70%│   │││
│  │ │ Cover Letter    │ [auto-generated]   │ 🟡 65%│   │││
│  │ │ Work Auth       │ [NOT FILLED]       │ 🔴 0% │   │││
│  │ │ Gender (EEO)    │ [NOT FILLED]       │ 🔴 0% │   │││
│  │ └──────────────────────────────────────────────────┘││
│  │                                                     ││
│  │ [✏️ Edit Values]  [▶️ Live Fill]  [📋 Copy Script] ││
│  └─────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

### 4. Profile (`/profile`)
```
┌─────────────────────────────────────────────────────────┐
│  ⚙️ Profile                                             │
│                                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Personal                                            ││
│  │ First Name: [João        ]  Last Name: [Silva     ]││
│  │ Email:      [joao@...    ]  Phone:    [+55119...  ]││
│  │ Location:   [São Paulo   ]  Country:  [Brazil     ]││
│  ├─────────────────────────────────────────────────────┤│
│  │ Skills                                              ││
│  │ [python] [rust] [nix] [kubernetes] [terraform]     ││
│  │ [+ Add Skill]                                       ││
│  ├─────────────────────────────────────────────────────┤│
│  │ Links                                               ││
│  │ LinkedIn: [https://linkedin.com/in/...]             ││
│  │ GitHub:   [https://github.com/...]                  ││
│  │ Portfolio:[https://...]                             ││
│  ├─────────────────────────────────────────────────────┤│
│  │ Preferences                                         ││
│  │ Remote:    [Remote Preferred ▼]                     ││
│  │ Min Salary: [120000]  Currency: [USD ▼]             ││
│  │ Titles: [Platform Engineer] [SRE] [+ Add]           ││
│  ├─────────────────────────────────────────────────────┤│
│  │ Resume                                              ││
│  │ [📄 curriculo.pdf]  [Upload New]                    ││
│  │  → Auto-extract: name, email, skills, experience    ││
│  └─────────────────────────────────────────────────────┘│
│                                                         │
│  [💾 Save Profile]                                      │
└─────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### REST

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/jobs/hunt` | Start job hunt with params (skills, sources, filters) |
| `GET` | `/api/jobs/hunt/{run_id}/status` | Check hunt progress |
| `GET` | `/api/jobs/list` | List scored jobs with filters (?source=, ?min_score=, ?status=, ?q=) |
| `GET` | `/api/jobs/{job_id}` | Job detail with full description |
| `POST` | `/api/jobs/{job_id}/apply` | Mark as applied |
| `POST` | `/api/jobs/{job_id}/status` | Update application status |
| `POST` | `/api/jobs/{job_id}/notes` | Add notes |
| `POST` | `/api/autofill/analyze` | Analyze a form URL, return field matches |
| `POST` | `/api/autofill/execute` | Execute live fill (opens browser) |
| `GET` | `/api/pipeline/stats` | Pipeline funnel statistics |
| `GET` | `/api/profile` | Get current profile |
| `PUT` | `/api/profile` | Update profile |
| `POST` | `/api/profile/resume` | Upload and parse resume |

### WebSocket

| Endpoint | Description |
|----------|-------------|
| `/ws/live` | Real-time crawl progress, log messages, job found events |

```json
// WebSocket messages:
{"type": "hunt_started", "total_sources": 5}
{"type": "source_done", "source": "greenhouse", "jobs_found": 34}
{"type": "job_found", "job": {...}}
{"type": "hunt_complete", "total_jobs": 200}
{"type": "error", "source": "lever", "message": "timeout"}
```

---

## File Structure

```
src/spider_nix/
├── server.py              # FastAPI app entrypoint
├── server/
│   ├── __init__.py
│   ├── routes/
│   │   ├── jobs.py        # /api/jobs/*
│   │   ├── pipeline.py    # /api/pipeline/*
│   │   ├── autofill.py    # /api/autofill/*
│   │   └── profile.py     # /api/profile/*
│   ├── ws.py              # WebSocket handler
│   └── templates/
│       ├── base.html       # Layout base (navbar, footer)
│       ├── index.html      # Job Hunt page
│       ├── pipeline.html   # Pipeline page
│       ├── autofill.html   # Auto-fill page
│       └── profile.html    # Profile page
└── static/
    └── app.js             # Minimal Alpine.js logic
```

---

## Launch

```bash
# Start the GUI
spider serve              # Lança em localhost:8000
spider serve --port 3000  # Porta customizada
spider serve --no-browser # Não abre navegador automaticamente
```

---

## Why Not Electron/Tauri Desktop App?

- **Zero configuração**: browser já tá instalado
- **Zero build**: sem compilar binário pra cada OS
- **Mais leve**: FastAPI + HTML pesa ~50MB, Electron ~200MB+
- **Remoto**: pode rodar no servidor e acessar de qualquer lugar
- **Progressivo**: se precisar de desktop app depois, empacota com PyInstaller + webview
