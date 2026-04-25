# Post LinkedIn — BESS Sizing Copilot v0.8.0

Versão humanizada (revisão 2). Ritmo de fala brasileira, sem estrutura "IA-perfeita".

---

## Texto principal

Tem uma coisa que ninguém fala sobre dimensionar BESS no Brasil: você precisa conhecer 4 regulamentos, 3 modalidades tarifárias e fazer uns 5 cálculos que dependem um do outro.

Construí um agente de IA que faz isso em conversa. 🔋

O mercado de armazenamento aqui tá num momento estranho — REN 1.000, Lei 14.300, mercado livre abrindo, demanda real por bateria... e a maioria dos integradores ainda dimensiona em planilha de Excel + memorial em Word. Caótico.

O que eu fiz foi um stack open-source com 4 partes:

Um núcleo Python determinístico — 162 testes em pytest, do sizing até Monte Carlo financeiro. Esse é o pé na realidade, não é alucinação de LLM.

Em cima dele, um agente conversacional (Claude + tool-use) que conduz a entrevista técnica, encadeia as ferramentas e monta a proposta executiva.

Um RAG BM25 sobre REN 1.000, Lei 14.300, NBR 13534 e a REH ANEEL mais recente da Enel SP — pra ele não inventar artigo nem valor de tarifa, que era um dos meus medos.

E um frontend Next.js + FastAPI que ainda exporta a proposta em PDF profissional, pra mandar pro cliente.

Coloquei pra rodar num caso real — indústria metalúrgica em Campinas, tarifas oficiais Enel A4 Verde da REH 3.477/2025. Acertou 6,5 dos 7 critérios técnicos que eu tinha listado. Mais interessante: o agente identificou um erro conceitual MEU na decomposição da economia (eu estava contando a TUSD da demanda contratada junto com a multa de ultrapassagem — double-counting). Tive que voltar e corrigir o prompt. Bom feedback loop.

Esse é o meu TCC. Mas o problema veio direto do dia-a-dia na HDT Energy, onde a gente atende cliente industrial que sofre com isso: vale o CAPEX? Quando paga? Como combinar peak shaving com arbitragem ACL?

Código, validações e roadmap aqui:
🔗 github.com/monkaS013/bess-sizing-copilot

Quem trabalha com energia ou com IA aplicada, dá uma olhada e me diz o que acharam — feedback é bem-vindo.

#BESS #ArmazenamentoDeEnergia #IAGenerativa #EnergiaBrasil #TCC #OpenSource #SetorElétrico

---

## O que mudei pra humanizar (pra você comparar)

| Antes (artificial) | Depois (humano) |
|---|---|
| "Dimensionar uma bateria industrial exige conhecer..." | "Tem uma coisa que ninguém fala..." |
| "está num inflection point" | "tá num momento estranho" |
| Bullets com "•" e ritmo simétrico | Frases corridas, alguns parágrafos longos, alguns curtos |
| "criaram demanda real" | "demanda real por bateria" |
| "errático, lento, opaco" (lista de 3) | "Caótico." (frase nominal seca) |
| "validei contra um caso real" | "coloquei pra rodar num caso real" |
| "motivou uma iteração no system prompt" | "tive que voltar e corrigir o prompt" |
| "lidando exatamente com decisões de" | "sofre com isso" |

Não inseri erros gramaticais — num post profissional eles prejudicam mais do que humanizam. O que tira a cara de IA é vocabulário oral + estrutura assimétrica + opinião própria, não erros propositais.

---

## Mídia: vídeo + PDF (3 opções por esforço)

### Opção A — Mínimo viável (5 minutos)

1 imagem só: screenshot do PDF aberto numa boa página (sugiro a página com a tabela de Sizing Recomendado + Indicadores Financeiros). Fundo cinza, sombra discreta. Pode fazer no Figma, PowerPoint ou Canva.

Pros: rápido, funciona.
Contras: estático, menos engajamento que vídeo.

### Opção B — Vídeo curto + 2-3 imagens (30-60 min) ⭐ recomendada

**Vídeo de 15-25 segundos** mostrando o uso real:

```
[0-3s]  abre o frontend localhost:3000
[3-8s]  cola uma pergunta no chat (versão curta do caso Enel)
[8-15s] tool calls aparecendo (expanders abrindo, agent pensando)
[15-20s] proposta executiva renderizada (rola pra mostrar tabelas)
[20-25s] click no botão "Baixar PDF da proposta"
[25-30s] PDF aberto
```

Ferramenta de gravação:
- **OBS Studio** (grátis, melhor qualidade, captura de janela)
- **ScreenToGif** (Windows nativo, simples, exporta GIF ou MP4)
- **Loom** (online, cria link compartilhável direto)

Anexa esse vídeo + 1 ou 2 screenshots do PDF aberto como segundo slide.

Pros: alcance algorítmico bem maior (LinkedIn favorece vídeo nativo em 2026).
Contras: 30-60 min de trabalho.

### Opção C — Carrossel completo (2-3 horas)

Carrossel de 6-8 slides em PDF (LinkedIn aceita PDF como carrossel):

1. **Capa**: "Construí um agente de IA pra dimensionar baterias industriais" (título grande + 1 linha de subtítulo)
2. **Problema**: "Por que dimensionar BESS no Brasil é difícil" (mostra os 4 regulamentos + 3 modalidades + 5 cálculos)
3. **Solução**: arquitetura visual (núcleo Python ↔ agente ↔ RAG ↔ frontend)
4. **Demo 1**: screenshot do chat com a tabela renderizada
5. **Demo 2**: screenshot do PDF gerado
6. **Validação**: "6,5/7 num caso real Enel SP"
7. **Stack técnico**: ícones de Python + Next + Claude + reportlab + rank_bm25
8. **CTA**: "github.com/monkaS013/bess-sizing-copilot"

Ferramenta: Figma ou Canva. Exporta como PDF e anexa direto no post.

Pros: visual mais profissional, agrega valor técnico maior, fica como portfolio.
Contras: 2-3h de design.

---

## Minha recomendação

**Opção B (vídeo + 2 imagens)**. O vídeo de 15-25s pega o engajamento do LinkedIn (que ama vídeo nativo agora), as imagens do PDF mostram o entregável real, e dá pra produzir em meia hora com OBS ou ScreenToGif.

Se quiser ir all-in pra defesa do TCC e ter material pra portfólio: **Opção C** vale o investimento.

---

## Notas práticas (mantidas da versão anterior)

**Tag da HDT Energy**: o LinkedIn não vai tagear automaticamente quando você colar o texto. Quando estiver editando o post, **apaga "HDT Energy" e digita manualmente** — vai aparecer sugestão da página da empresa pra você selecionar.

**Melhor horário**: Terça-feira 09h-10h ou Quinta-feira 11h-12h (BR). Evita 6ª tarde / fim de semana.

**Boost com primeiro comentário** — 5min depois de publicar, comente algo bem específico tecnicamente:

> Detalhe técnico: o RAG usa BM25 puro Python ao invés de embeddings. Pra corpus pequeno e curado de regulamentos, BM25 dá precisão maior em PT-BR sem dependência de modelo de 100MB. Embeddings ficam pro v2 se eu encontrar caso onde preciso de busca semântica.

Esse comentário fixa o engagement e dá ar de "expert que pensou no trade-off".

**Não tagueia colegas no post** — fica forçado. Se quiser que pessoas específicas vejam, marca elas no comentário pedindo feedback.
