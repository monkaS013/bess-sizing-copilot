# Setup Supabase — passo a passo

Persistência das sessões do BESS Sizing Copilot (Sprint 3 Fase C). Sem este setup, o sistema funciona em memória — perde tudo ao reiniciar o backend. **Com Supabase**, sessões e mensagens sobrevivem entre reinícios e podem ser auditadas no painel.

Tempo total estimado: 10-15 minutos. Free tier suficiente.

---

## 1. Criar conta + projeto

1. Acessa https://supabase.com → **Start your project** (canto superior direito)
2. Login com GitHub recomendado (sem senha pra criar)
3. Após login: **+ New Project**
4. Configura:
   - **Project name:** `bess-sizing-copilot`
   - **Database password:** gera uma forte e **copia em local seguro** (1Password, etc) — só vai precisar se quiser conexão direta no Postgres no futuro
   - **Region:** `South America (São Paulo)` — menor latência do Brasil
   - **Pricing plan:** Free
5. Clica **Create new project**. Provisão demora ~1-2 minutos.

## 2. Copiar as credenciais

Quando o projeto subir, vai pra **Project Settings → API** (ícone de engrenagem no canto inferior esquerdo, depois "API" no menu).

Vai precisar de **3 valores**:

| O que | Onde tá no painel | Onde usar |
|-------|-------------------|-----------|
| **Project URL** | URL no topo (ex: `https://xxxxxx.supabase.co`) | `SUPABASE_URL` (backend) e `NEXT_PUBLIC_SUPABASE_URL` (frontend) |
| **anon public** key | Bloco "Project API keys" → primeira key | `NEXT_PUBLIC_SUPABASE_ANON_KEY` (frontend) |
| **service_role secret** key | Bloco "Project API keys" → segunda key, escondida (precisa clicar em "Reveal") | `SUPABASE_SERVICE_ROLE_KEY` (backend) |

⚠️ **A `service_role` key bypassa RLS e tem privilégios de admin.** Nunca commite ela no git, nunca exponha no frontend, só no `.env` do backend.

## 3. Aplicar a migration SQL

A migration cria as 3 tabelas (`sessoes_bess`, `mensagens`, `agente_logs`), índices, triggers e Row-Level Security.

1. No painel Supabase, vai em **SQL Editor** (ícone de banco no sidebar)
2. Clica em **+ New query**
3. Abre o arquivo local `supabase/migrations/0001_init.sql` (no projeto Windows: `C:\Users\Vinicius\Desktop\Projeto HDT\supabase\migrations\0001_init.sql`)
4. Cola **TODO** o conteúdo no editor SQL
5. Clica **Run** (ou Ctrl+Enter)

Esperado: na parte de baixo aparece uma tabelinha:

| tabela | registros |
|--------|-----------|
| sessoes_bess | 0 |
| mensagens | 0 |
| agente_logs | 0 |

Se aparecer erro, **copia o erro** e me manda — provavelmente algum nome conflitando com objeto pré-existente, dá pra resolver com `drop table if exists` antes.

## 4. Habilitar Anonymous Auth

No painel Supabase: **Authentication → Providers → Anonymous Sign-Ins**.

Por default vem **desabilitado**. Habilita o toggle e clica **Save**.

Sem isso, o frontend vai cair no fallback de UUID local (não vai persistir no Supabase).

## 5. Configurar env vars no backend Python

```powershell
cd "C:\Users\Vinicius\Desktop\Projeto HDT\agent"
notepad .env
```

Adiciona/atualiza essas duas linhas (mantendo `ANTHROPIC_API_KEY` que já está):

```
SUPABASE_URL=https://xxxxxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
```

Salva. Reinicia o uvicorn.

**Esperado no log:**

```
Storage backend: SupabaseStorage    ← antes era InMemoryStorage
API key carregada: sk-ant-api03-...
```

## 6. Configurar env vars no frontend Next.js

```powershell
cd "C:\Users\Vinicius\Desktop\Projeto HDT\frontend"
notepad .env.local
```

Adiciona:

```
BESS_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGc...
```

Note os prefixos:
- **`NEXT_PUBLIC_*`** = exposto ao navegador (anon key é segura para isso, é só permissão de leitura via RLS)
- **Sem prefixo** (`BESS_API_URL`) = só server-side

Salva. **Reinicia o `npm run dev`** (importante: env vars do Next.js só recarregam ao restartar o dev server, não com hot reload).

## 7. Testar

Recarrega `http://localhost:3000`. Conversa rapidinho com o agente.

**Validações:**

A) **Console do navegador** (F12 → Console) — deve estar sem warnings sobre `signInAnonymously`. Se aparecer aviso, é porque você esqueceu de habilitar Anonymous Sign-Ins no passo 4.

B) **Sidebar do frontend** — agora deve mostrar `Storage: Supabase` em vez de `Storage: InMemory`.

C) **Tabela no Supabase** — abre **Table Editor** no painel Supabase → seleciona `sessoes_bess`. Você deve ver **1 linha** com seu `usuario_id` (auth.uid() do anonymous).

D) **Mensagens persistidas** — clica em `mensagens` na tabela. Deve ter **2 linhas por mensagem que você mandou** (1 user + 1 assistant), com `tool_calls` em JSONB se o agente chamou tools.

E) **Survives restart** — para o uvicorn (Ctrl+C), sobe de novo. Recarrega a página. **Sua sessão ainda existe**, mensagens antigas continuam acessíveis (via `GET /api/sessions/{id}/historico`).

## Troubleshooting

**"signInAnonymously falhou"** → Anonymous Auth desabilitado. Volta no passo 4.

**Sidebar continua "InMemoryStorage" mesmo com env vars setadas** → Reiniciou o uvicorn? Conferiu se o `.env` do `agent/` tem as 2 linhas? `cat $env:USERPROFILE\Desktop\"Projeto HDT"\agent\.env` deveria mostrar.

**RLS error: "new row violates row-level security policy"** → significa que o backend está tentando inserir sem `usuario_id` ou com `usuario_id` diferente de `auth.uid()`. Confirma que o frontend está passando `X-User-Id` corretamente nas chamadas.

**Postgres connection error** → algo errado com a SUPABASE_URL ou service_role key. Confere no painel: **Project Settings → API**.

**postgrest.exceptions.APIError** → código de erro específico do Postgres. Geralmente vem com mensagem detalhada — copia e me manda.

## Custo

- **Free tier:** 500 MB de DB, 50k usuários ativos/mês, 1GB de bandwidth saindo. **Mais que suficiente** pra MVP local + alguns demos.
- **Pro tier:** $25/mês quando precisar escalar. Sem urgência.

## Próximos passos (opcionais)

- **Habilitar email auth** se quiser que o usuário possa "linkar" sua sessão anônima à conta dele depois (recover sessões cross-device).
- **Cron job** que arquiva sessões antigas (status='ativa' há > 30 dias → 'arquivada').
- **Dashboard** com queries em `agente_logs` para ver tools mais usadas, custo médio por sessão, latência típica.
