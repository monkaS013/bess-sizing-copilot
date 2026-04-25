# Resolução Homologatória ANEEL nº 3.477/2025 — Reajuste Tarifário Enel SP

**Fonte oficial:** ANEEL — Reajuste Tarifário Anual 2025 da Enel Distribuição São Paulo
**Vigência:** desde 04/07/2025
**Efeito médio:** +15,77%
**Aplicação:** todas as classes tarifárias atendidas pela Enel SP (ex-Eletropaulo),
incluindo o Estado de São Paulo, exceto unidades atendidas por outras
distribuidoras (CPFL, EDP).

## Tarifas oficiais — Classe A4, Modalidade Verde

Aplicável a indústrias, hospitais e comércio atendidos em 2,3-25 kV.

### Componentes de demanda (R$/kW/mês)

| Componente | Valor |
|------------|-------|
| TUSD demanda contratada | R$ 17,04/kW |
| Multa de ultrapassagem (2× TUSD por REN 1.000 Art. 60) | R$ 34,08/kW |

### Componentes de energia (R$/MWh)

| Componente | Valor |
|------------|-------|
| TUSD energia — ponta | R$ 837,07 / MWh = R$ 0,83707/kWh |
| TUSD energia — fora-ponta | R$ 125,05 / MWh = R$ 0,12505/kWh |
| TE energia — ponta | R$ 439,13 / MWh = R$ 0,43913/kWh |
| TE energia — fora-ponta | R$ 273,54 / MWh = R$ 0,27354/kWh |

### Tarifas totais (TUSD + TE)

| Componente | Valor |
|------------|-------|
| Tarifa total energia ponta | R$ 1,2762/kWh ≈ R$ 1,28/kWh |
| Tarifa total energia fora-ponta | R$ 0,3986/kWh ≈ R$ 0,40/kWh |
| **Spread ponta − fora-ponta** | **R$ 0,8776/kWh ≈ R$ 0,88/kWh** |

## Horário tarifário de ponta (modalidade Verde)

Para Enel SP A4:
- **Ponta**: 18h00 às 20h59 (3 horas de segunda a sábado, exceto feriados)
- **Fora-ponta**: demais 21 horas

## Implicação para BESS

Para um cliente A4 Verde Enel SP que paga ultrapassagem (200 kW excedente):

| Parcela de economia | Cálculo | Valor anual |
|---------------------|---------|-------------|
| Multa ultrapassagem evitada | 200 × R$ 34,08 × 12 meses | R$ 81.792 |
| Spread tarifário ponta→fora-ponta (hipotético 78 MWh deslocados/ano) | 78.000 × R$ 0,88 | R$ 68.640 |
| **Total (peak shaving puro)** | | **R$ 150.432/ano** |

**Importante**: a multa de ultrapassagem (R$ 34,08/kW) é o valor ADICIONAL
pago hoje sobre o excedente. Eliminá-la sozinha já captura toda a economia
da parcela "demanda" da fatura. NÃO somar com a TUSD da demanda contratada
(R$ 17,04/kW × 200 = R$ 40.896) — isso seria double-counting porque a TUSD
da demanda contratada continua sendo paga sobre os 600 kW contratados
independente do BESS estar instalado.

## Comparação com outras distribuidoras (referência)

Em outras concessões do Sudeste, a TUSD A4 Verde varia tipicamente entre
R$ 14 e R$ 24/kW (dados 2024-2025), e a tarifa total de energia ponta entre
R$ 1,10 e R$ 1,45/kWh. Sempre buscar a REH mais recente da distribuidora
específica do cliente.

## Atualização

Esta REH é específica de **Julho 2025**. Reajustes anuais ocorrem normalmente
no aniversário da concessão (janeiro-julho dependendo da concessionária).
Verificar https://www.gov.br/aneel/pt-br/assuntos/tarifas para versão vigente.

## Tags principais (para retrieval)

Enel SP, Eletropaulo, A4 Verde, modalidade verde, ultrapassagem 34,08,
TUSD 17,04, REH 3477, REH 2025, tarifa ponta 1,28, tarifa fora-ponta 0,40,
spread 0,88, horário de ponta 18h, indústria SP, hospital SP, Campinas,
Sorocaba, Sudeste tarifa.
