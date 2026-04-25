# ============================================================================
# init-git.ps1
# Inicializa o repositório git para o BESS Sizing Copilot e cria a tag v1.0.0.
#
# Uso:
#   1. Abrir PowerShell na pasta C:\Users\Vinicius\Desktop\Projeto HDT
#   2. Permitir scripts (uma vez):
#        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   3. Rodar:
#        .\scripts\init-git.ps1
#
# Pré-requisitos:
#   - Git instalado (https://git-scm.com)
#   - Pasta deve estar limpa (sem .git anterior do Cowork sandbox)
# ============================================================================

$ErrorActionPreference = "Stop"

# Garantir que estamos na raiz correta
$projectRoot = "C:\Users\Vinicius\Desktop\Projeto HDT"
Set-Location $projectRoot
Write-Host "Working directory: $projectRoot" -ForegroundColor Cyan

# 1. Limpar .git eventualmente corrompido pelo sandbox FUSE
if (Test-Path ".git") {
    Write-Host "[1/6] Removendo .git inválido criado pelo sandbox..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".git"
}

# 2. Inicializar repo
Write-Host "[2/6] git init -b main" -ForegroundColor Cyan
git init -b main

# 3. Configurar usuário (local ao repo)
Write-Host "[3/6] Configurando usuário local..." -ForegroundColor Cyan
git config user.name "Vinicius Morais"
git config user.email "vinicius.morais@hdt.energy"

# 4. Adicionar tudo
Write-Host "[4/6] git add ." -ForegroundColor Cyan
git add .
git status --short

# 5. Commit zero
Write-Host "[5/6] Commit zero..." -ForegroundColor Cyan
$commitMessage = @"
v1.0.0: nucleo deterministico completo (Sprints 1.1-1.4)

Sprint 1.1 - Dimensionamento
  - dimensionar_peak_shaving / arbitragem / backup
  - 3 dataclasses imutaveis com premissas auditaveis

Sprint 1.2 - Despacho horario (8760h)
  - simular_despacho_horario com 3 estrategias
  - peak_shaving (greedy otimo), arbitragem (percentil), autoconsumo_hibrido
  - Conservacao de energia validada (E_c*eta_c - E_d/eta_d = dSoC*E_nom)

Sprint 1.3 - Analise financeira
  - analisar_financeiro: payback simples/descontado, TIR (bisseccao), VPL, LCOS
  - Sensibilidade tornado +-20% em CAPEX/OPEX/economia/WACC
  - Zero dependencias externas

Sprint 1.4 - Degradacao SoH(t)
  - calcular_soh_anual: calendarico + ciclico + Arrhenius
  - Defaults LFP/NMC/LTO calibrados contra Tier 1 (Huawei LUNA2000)
  - EoL @ 80% SoH com interpolacao linear

Stack:
  - 13 funcoes/classes publicas
  - 141 testes pytest, 0,3s de execucao
  - 5 memoriais tecnicos (~3000 linhas markdown)
  - Zero dependencias externas (so math + dataclasses)
"@

git commit -m $commitMessage

# 6. Tag v1.0.0 anotada
Write-Host "[6/6] Criando tag v1.0.0..." -ForegroundColor Cyan
git tag -a v1.0.0 -m "v1.0.0: nucleo deterministico completo - Sprints 1.1 a 1.4"

# Resumo final
Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " REPOSITORIO INICIALIZADO COM SUCESSO" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
git log --oneline --decorate --all
Write-Host ""
git tag
Write-Host ""
Write-Host "Proximos passos para publicar no GitHub:" -ForegroundColor Yellow
Write-Host "  1. Criar repo vazio em https://github.com/monkaS013/bess-sizing-copilot"
Write-Host "  2. Conectar:"
Write-Host "       git remote add origin git@github.com:monkaS013/bess-sizing-copilot.git"
Write-Host "  3. Push branch + tag:"
Write-Host "       git push -u origin main"
Write-Host "       git push origin v1.0.0"
