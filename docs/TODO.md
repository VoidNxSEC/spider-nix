# TODO: Professional Autofill System

## Phase 1 — Robust Field Matching (Alta prioridade)

### 1.1 Label-based matching
Atualmente o matcher só olha `name` do campo. Deve também parsear o `<label>` associado.

```
<input name="field_42" id="field_42">
<label for="field_42">First Name *</label>
```
→ "First Name" é muito mais informativo que "field_42"

**Ação:** Estender `FieldMatcher` pra receber pares `(label_text, field_name)` e pontuar ambos.

### 1.2 Confidence scoring por campo
Cada match deve ter score de confiança (0-1), não só match/não-match.

```
"full_name"       → "name"        = confiança 0.9
"first_name"      → "name"        = confiança 0.5 (pode ser first ou full)
"resume_upload"   → "resume"      = confiança 0.95
"field_abc_123"   → sem label     = confiança 0.0 (não preencher)
```

**Ação:** `FieldMatcher.match()` retorna `(profile_attr, confidence)` em vez de só `profile_attr`.

### 1.3 ATS-specific field maps
Cada ATS tem nomes de campo previsíveis. Criar templates:

```python
GREENHOUSE_FIELDS = {
    "first_name": ["first_name", "firstName", "candidate_first_name"],
    "last_name":  ["last_name", "lastName", "candidate_last_name"],
    "email":      ["email", "candidate_email", "email_address"],
    "resume":     ["resume", "resume_upload", "attachments[0]"],
    "cover_letter": ["cover_letter", "cover_letter_text"],
    "linkedin":   ["linkedin_url", "url_linkedin", "question_12345"],
    ...
}
```

**Ação:** `FieldMatcher` detecta plataforma e aplica template específico primeiro.

---

## Phase 2 — Live Interactive Mode (Alta prioridade)

### 2.1 Playwright live executor
Em vez de gerar script `.py`, executar direto:

```bash
spider autofill https://jobs.lever.co/empresa/vaga \
  --profile me.json --use-chrome --live
```

Fluxo:
1. Abre Chrome com perfil do usuário
2. Navega até a URL
3. Detecta qual ATS/platforma é
4. Preenche campos com alta confiança (>0.8) automaticamente
5. Destaca campos com confiança média (0.5-0.8) em **amarelo** pra revisão
6. Campos com baixa confiança (<0.5) ficam em **branco** pra preenchimento manual
7. Pausa e espera o usuário revisar
8. Usuário pressiona Enter no terminal → submeter, ou Esc → pular

**Ação:** Criar `LiveFormFiller` que usa Playwright direto com interação via terminal.

### 2.2 Visual feedback no browser
Injetar script no page que:
- Borda verde = preenchido com alta confiança
- Borda amarela = preenchido com confiança média (revisar)
- Borda vermelha = não preenchido (manual)
- Tooltip mostrando de onde veio o valor

---

## Phase 3 — Template Knowledge Base (Média prioridade)

### 3.1 Common ATS field database
Criar um JSON/YAML com mapeamentos conhecidos:

```yaml
# greenhouse.yaml
greenhouse:
  fields:
    first_name: [first_name, firstName, candidateFirstName]
    last_name: [last_name, lastName, candidateLastName]
    email: [email, candidateEmail]
    ...
  multi_step: false
  has_eeo: true
  captcha: false
  file_upload: true

# lever.yaml
lever:
  fields:
    name: [name, fullName]
    email: [email, candidateEmail]
    ...
  multi_step: false
  has_eeo: true
```

### 3.2 Auto-detect platform
Ao carregar a página, detectar por URL/DOM:
- `boards.greenhouse.io` → template Greenhouse
- `jobs.lever.co` → template Lever
- `jobs.ashbyhq.com` → template Ashby
- `<meta name="ats"` → usar meta tag
- Senão → modo genérico (label matching)

---

## Phase 4 — Resume Parsing (Média prioridade)

### 4.1 Extract data from PDF/DOCX resume
Usar `pymupdf` ou `pdfplumber` pra extrair texto do CV e popular o perfil:

```bash
spider job-profile --from-resume curriculo.pdf
# → Extrai: nome, email, telefone, skills, experiência, educação
# → Popula AutoFillProfile automaticamente
```

### 4.2 Smart field filling from resume
Pra campos como "Tell us about yourself" ou "Why do you want to work here?", usar chunks relevantes do CV.

---

## Phase 5 — Frontend GUI (Média prioridade)

Ver [GUI_DESIGN.md](GUI_DESIGN.md) para arquitetura completa.

---

## Quick Wins (Baixo esforço, alto impacto)

- [x] Suporte a Chrome profile (`--use-chrome`)
- [x] Field matching por nome de campo
- [x] Label matching (Phase 1.1)
- [x] Live mode (Phase 2.1)
- [x] ATS-specific templates (Phase 3.1)
- [x] External YAML template knowledge base (Phase 3)
- [x] Command grouping (`spider job *`) (DX consolidation)
- [x] Status dashboard (`spider status`)
