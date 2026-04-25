"""
tools.py - Wrappers JSON-friendly de bess-core para Anthropic tool-use.

Cada tool tem:
  - definition (JSON Schema input + descricao)
  - executor (funcao Python que recebe o input dict e devolve dict serializavel)

Convencoes:
  - Inputs e outputs em JSON puro (sem dataclasses, sem numpy).
  - Outputs grandes (perfis horarios) sao SUMARIZADOS antes de devolver
    ao agente -- so devolve metricas + amostras pontuais para o LLM
    nao consumir contexto desnecessariamente.
  - Tools de geracao de perfil retornam o perfil completo so para uso
    INTERNO do encadeamento (o agente passa o perfil_id de volta, nao
    o array inteiro).
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

# Adicionar bess-core ao path (estamos em agent/, bess-core eh sibling)
_ROOT = Path(__file__).resolve().parent.parent
_BESS_CORE = _ROOT / "bess-core"
if str(_BESS_CORE) not in sys.path:
    sys.path.insert(0, str(_BESS_CORE))

from bess_core import (
    analisar_financeiro,
    calcular_soh_anual,
    dimensionar_arbitragem,
    dimensionar_backup,
    dimensionar_peak_shaving,
    simulacao_monte_carlo,
    simular_despacho_horario,
)
from perfis import (
    curva_fv_diaria,
    perfil_comercial_semanal,
    perfil_industrial_semanal,
    replicar_para_ano,
)


# ---------------------------------------------------------------------------
# Cache de perfis (para evitar passar arrays gigantes ao LLM)
# ---------------------------------------------------------------------------

_PERFIL_CACHE: dict[str, list[float]] = {}


def _registrar_perfil(perfil_id: str, valores: list[float]) -> None:
    _PERFIL_CACHE[perfil_id] = valores


def _resgatar_perfil(perfil_id: str) -> list[float]:
    if perfil_id not in _PERFIL_CACHE:
        raise ValueError(
            f"perfil_id '{perfil_id}' nao existe. Gere o perfil primeiro "
            f"com gerar_perfil_industrial ou gerar_perfil_comercial."
        )
    return _PERFIL_CACHE[perfil_id]


def _resumir_perfil(valores: list[float]) -> dict:
    """Retorna estatisticas-resumo de um perfil (em vez do array todo)."""
    n = len(valores)
    return {
        "n_horas": n,
        "min_kw": round(min(valores), 1),
        "max_kw": round(max(valores), 1),
        "media_kw": round(sum(valores) / n, 1),
        "amostra_24h": [round(v, 1) for v in valores[:24]],
    }


def limpar_cache() -> None:
    """Util para testes."""
    _PERFIL_CACHE.clear()


# ===========================================================================
# Tool 1: gerar_perfil_industrial
# ===========================================================================

DEF_GERAR_PERFIL_INDUSTRIAL = {
    "name": "gerar_perfil_industrial",
    "description": (
        "Gera um perfil semanal de carga (168h) para industria. "
        "Use quando o usuario descreve o caso em linguagem natural mas nao "
        "tem dados de medicao horaria. Devolve um perfil_id que pode ser "
        "usado nas demais tools que precisam de perfil_carga_horario."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "perfil_id": {
                "type": "string",
                "description": "Identificador unico (ex: 'industria_500kw').",
            },
            "base_dia_util_kw": {"type": "number", "description": "Carga base fora do pico (kW)."},
            "base_fim_semana_kw": {"type": "number", "description": "Carga base no fim de semana (kW)."},
            "pico_kw": {"type": "number", "description": "Carga durante o pico (kW)."},
            "hora_inicio_pico": {"type": "integer", "description": "Hora do dia em que o pico comeca (0-23)."},
            "duracao_pico_h": {"type": "integer", "description": "Duracao do pico em horas."},
            "dias_uteis": {"type": "integer", "default": 5, "description": "Quantidade de dias uteis (default 5)."},
        },
        "required": ["perfil_id", "base_dia_util_kw", "base_fim_semana_kw", "pico_kw", "hora_inicio_pico", "duracao_pico_h"],
    },
}


def exec_gerar_perfil_industrial(args: dict) -> dict:
    perfil = perfil_industrial_semanal(
        base_dia_util_kw=args["base_dia_util_kw"],
        base_fim_semana_kw=args["base_fim_semana_kw"],
        pico_kw=args["pico_kw"],
        hora_inicio_pico=args["hora_inicio_pico"],
        duracao_pico_h=args["duracao_pico_h"],
        dias_uteis=args.get("dias_uteis", 5),
    )
    _registrar_perfil(args["perfil_id"], perfil)
    return {
        "perfil_id": args["perfil_id"],
        "resumo": _resumir_perfil(perfil),
    }


# ===========================================================================
# Tool 2: dimensionar_peak_shaving
# ===========================================================================

DEF_DIMENSIONAR_PEAK_SHAVING = {
    "name": "dimensionar_peak_shaving",
    "description": (
        "Dimensiona um BESS para corte de demanda (peak shaving). Calcula "
        "energia util, energia nominal, potencia e C-rate. Use apos ter "
        "gerado um perfil_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "perfil_id": {"type": "string", "description": "ID do perfil gerado anteriormente."},
            "demanda_contratada_kw": {"type": "number", "description": "Demanda contratada com a distribuidora (kW). Limite que o BESS deve manter."},
            "tarifa_demanda_brl_kw": {"type": "number", "description": "Tarifa de demanda em R$/kW."},
            "dod": {"type": "number", "default": 0.9},
            "eficiencia_rt": {"type": "number", "default": 0.92},
            "reserva_tecnica": {"type": "number", "default": 0.10},
        },
        "required": ["perfil_id", "demanda_contratada_kw", "tarifa_demanda_brl_kw"],
    },
}


def exec_dimensionar_peak_shaving(args: dict) -> dict:
    perfil = _resgatar_perfil(args["perfil_id"])
    r = dimensionar_peak_shaving(
        perfil_carga_horario=perfil,
        demanda_contratada_kw=args["demanda_contratada_kw"],
        tarifa_demanda_brl_kw=args["tarifa_demanda_brl_kw"],
        dod=args.get("dod", 0.9),
        eficiencia_rt=args.get("eficiencia_rt", 0.92),
        reserva_tecnica=args.get("reserva_tecnica", 0.10),
    )
    return {
        "energia_util_kwh": round(r.energia_util_kwh, 1),
        "energia_nominal_kwh": round(r.energia_nominal_kwh, 1),
        "potencia_kw": round(r.potencia_kw, 1),
        "c_rate": round(r.c_rate, 3),
        "p_shave_kw": round(r.p_shave_kw, 1),
        "n_eventos_pico_no_perfil": r.n_eventos_pico,
    }


# ===========================================================================
# Tool 3: dimensionar_arbitragem
# ===========================================================================

DEF_DIMENSIONAR_ARBITRAGEM = {
    "name": "dimensionar_arbitragem",
    "description": (
        "Dimensiona um BESS para arbitragem temporal de energia (mercado livre). "
        "Recebe potencia alvo e duracao de descarga."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "potencia_alvo_kw": {"type": "number"},
            "duracao_descarga_h": {"type": "number"},
            "ciclos_dia": {"type": "number", "default": 1.0},
        },
        "required": ["potencia_alvo_kw", "duracao_descarga_h"],
    },
}


def exec_dimensionar_arbitragem(args: dict) -> dict:
    r = dimensionar_arbitragem(
        potencia_alvo_kw=args["potencia_alvo_kw"],
        duracao_descarga_h=args["duracao_descarga_h"],
        ciclos_dia=args.get("ciclos_dia", 1.0),
    )
    return {
        "energia_util_kwh": round(r.energia_util_kwh, 1),
        "energia_nominal_kwh": round(r.energia_nominal_kwh, 1),
        "potencia_kw": round(r.potencia_kw, 1),
        "c_rate": round(r.c_rate, 3),
        "throughput_anual_kwh": round(r.energia_throughput_anual_kwh, 0),
    }


# ===========================================================================
# Tool 4: dimensionar_backup
# ===========================================================================

DEF_DIMENSIONAR_BACKUP = {
    "name": "dimensionar_backup",
    "description": (
        "Dimensiona um BESS para backup de cargas criticas (UPS-like). "
        "Defaults mais conservadores que peak shaving (DoD 0.95, reserva 20%)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "carga_critica_kw": {"type": "number"},
            "autonomia_h": {"type": "number"},
        },
        "required": ["carga_critica_kw", "autonomia_h"],
    },
}


def exec_dimensionar_backup(args: dict) -> dict:
    r = dimensionar_backup(
        carga_critica_kw=args["carga_critica_kw"],
        autonomia_h=args["autonomia_h"],
    )
    return {
        "energia_util_kwh": round(r.energia_util_kwh, 1),
        "energia_nominal_kwh": round(r.energia_nominal_kwh, 1),
        "potencia_kw": round(r.potencia_kw, 1),
        "c_rate": round(r.c_rate, 3),
    }


# ===========================================================================
# Tool 5: simular_despacho
# ===========================================================================

DEF_SIMULAR_DESPACHO = {
    "name": "simular_despacho",
    "description": (
        "Simula despacho horario do BESS sobre um perfil. Estrategia "
        "'peak_shaving' eh a mais comum -- exige threshold_kw. Devolve "
        "metricas agregadas (energia carregada/descarregada, ciclos, perdas, "
        "demanda residual maxima). NAO retorna o array horario completo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "perfil_id": {"type": "string"},
            "capacidade_nominal_kwh": {"type": "number"},
            "potencia_kw": {"type": "number"},
            "estrategia": {"type": "string", "enum": ["peak_shaving", "arbitragem", "autoconsumo_hibrido"]},
            "threshold_kw": {"type": "number", "description": "Obrigatorio se estrategia=peak_shaving."},
            "soc_inicial": {"type": "number", "default": 0.5},
        },
        "required": ["perfil_id", "capacidade_nominal_kwh", "potencia_kw", "estrategia"],
    },
}


def exec_simular_despacho(args: dict) -> dict:
    perfil = _resgatar_perfil(args["perfil_id"])
    kwargs: dict[str, Any] = {}
    if args["estrategia"] == "peak_shaving":
        if "threshold_kw" not in args:
            raise ValueError("threshold_kw eh obrigatorio para peak_shaving.")
        kwargs["threshold_kw"] = args["threshold_kw"]
    r = simular_despacho_horario(
        perfil_carga_kw=perfil,
        capacidade_nominal_kwh=args["capacidade_nominal_kwh"],
        potencia_kw=args["potencia_kw"],
        estrategia=args["estrategia"],
        soc_inicial=args.get("soc_inicial", 0.5),
        **kwargs,
    )
    return {
        "energia_carregada_kwh": round(r.energia_carregada_kwh, 1),
        "energia_descarregada_kwh": round(r.energia_descarregada_kwh, 1),
        "energia_grid_importada_kwh": round(r.energia_grid_importada_kwh, 1),
        "ciclos_equivalentes": round(r.ciclos_equivalentes, 3),
        "perdas_kwh": round(r.perdas_kwh, 1),
        "delta_soc": round(r.delta_soc, 3),
        "demanda_residual_max_kw": round(max(r.demanda_apos_bess_kw), 1),
        "horizonte_horas": len(r.p_carga_kw),
    }


# ===========================================================================
# Tool 6: analisar_financeiro
# ===========================================================================

DEF_ANALISAR_FINANCEIRO = {
    "name": "analisar_financeiro",
    "description": (
        "Calcula payback (simples e descontado), TIR, VPL e LCOS para o "
        "projeto. Tipico chamar apos dimensionar e simular despacho. "
        "Sempre informe estimativas de CAPEX, OPEX, economia e energia "
        "descarregada anual."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "capex_brl": {"type": "number"},
            "opex_anual_brl": {"type": "number"},
            "economia_anual_brl": {"type": "number"},
            "energia_descarregada_anual_kwh": {"type": "number"},
            "horizonte_anos": {"type": "integer", "default": 20},
            "wacc": {"type": "number", "default": 0.12},
        },
        "required": ["capex_brl", "opex_anual_brl", "economia_anual_brl", "energia_descarregada_anual_kwh"],
    },
}


def exec_analisar_financeiro(args: dict) -> dict:
    r = analisar_financeiro(
        capex_brl=args["capex_brl"],
        opex_anual_brl=args["opex_anual_brl"],
        economia_anual_brl=args["economia_anual_brl"],
        energia_descarregada_anual_kwh=args["energia_descarregada_anual_kwh"],
        horizonte_anos=args.get("horizonte_anos", 20),
        wacc=args.get("wacc", 0.12),
    )
    return {
        "payback_simples_anos": round(r.payback_simples_anos, 2) if r.payback_simples_anos else None,
        "payback_descontado_anos": round(r.payback_descontado_anos, 2) if r.payback_descontado_anos else None,
        "tir_percent": round(r.tir_percent, 2) if r.tir_percent else None,
        "vpl_brl": round(r.vpl_brl, 0),
        "lcos_brl_mwh": round(r.lcos_brl_mwh, 0),
        "viavel": r.vpl_brl > 0,
        "tornado_sensibilidade": [
            {
                "variavel": item.variavel,
                "vpl_baixo": round(item.vpl_baixo_brl, 0),
                "vpl_central": round(item.vpl_central_brl, 0),
                "vpl_alto": round(item.vpl_alto_brl, 0),
            }
            for item in r.sensibilidade
        ],
    }


# ===========================================================================
# Tool 7: calcular_soh
# ===========================================================================

DEF_CALCULAR_SOH = {
    "name": "calcular_soh",
    "description": (
        "Calcula a evolucao do State of Health (SoH) do banco ao longo do "
        "horizonte, com ajuste de Arrhenius (temperatura) e DoD. Devolve "
        "EoL @ 80%% e curva ano-a-ano."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "quimica": {"type": "string", "enum": ["LFP", "NMC", "LTO"], "default": "LFP"},
            "dod_medio": {"type": "number", "default": 0.80},
            "ciclos_ano": {"type": "number", "default": 365},
            "temperatura_celsius": {"type": "number", "default": 25.0},
            "horizonte_anos": {"type": "integer", "default": 20},
        },
        "required": [],
    },
}


def exec_calcular_soh(args: dict) -> dict:
    r = calcular_soh_anual(
        quimica=args.get("quimica", "LFP"),
        dod_medio=args.get("dod_medio", 0.80),
        ciclos_ano=args.get("ciclos_ano", 365),
        temperatura_celsius=args.get("temperatura_celsius", 25.0),
        horizonte_anos=args.get("horizonte_anos", 20),
    )
    return {
        "soh_anual": [round(s, 4) for s in r.soh_anual],
        "eol_anos": round(r.eol_anos, 2) if r.eol_anos else None,
        "k_cal_eff_pct_ano": round(r.k_cal_eff * 100, 4),
        "k_cyc_eff_pct_ciclo": round(r.k_cyc_eff * 100, 5),
    }


# ===========================================================================
# Tool 8: match_sku_huawei (hardcoded simples para MVP)
# ===========================================================================

DEF_MATCH_SKU_HUAWEI = {
    "name": "match_sku_huawei",
    "description": (
        "Sugere SKU Huawei LUNA2000 compativel com o sizing. Hardcoded "
        "para MVP - linha completa fica para integracao FusionSolar API."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "energia_nominal_kwh": {"type": "number"},
            "potencia_kw": {"type": "number"},
        },
        "required": ["energia_nominal_kwh", "potencia_kw"],
    },
}


_HUAWEI_SKUS = [
    # (faixa de aplicacao em kWh nominal, definida para evitar misfit grosseiro)
    {"sku": "LUNA2000-5KWH-RES",     "kwh_modulo": 5,    "kw_pcs": 5,    "kwh_min": 0,     "kwh_max": 50},
    {"sku": "LUNA2000-S1-200KWH",    "kwh_modulo": 200,  "kw_pcs": 100,  "kwh_min": 50,    "kwh_max": 1500},
    {"sku": "LUNA2000-S0-2.0MWH",    "kwh_modulo": 2000, "kw_pcs": 1000, "kwh_min": 1500,  "kwh_max": 100_000},
]


def exec_match_sku_huawei(args: dict) -> dict:
    energia = args["energia_nominal_kwh"]
    potencia = args["potencia_kw"]
    candidatos = []
    for sku in _HUAWEI_SKUS:
        # Filtro de faixa de aplicacao para evitar misfit grosseiro.
        if not (sku["kwh_min"] <= energia <= sku["kwh_max"]):
            continue
        n_modulos_e = max(1, round(energia / sku["kwh_modulo"] + 0.499))  # arredonda p/ cima
        n_pcs = max(1, round(potencia / sku["kw_pcs"] + 0.499))
        e_total = n_modulos_e * sku["kwh_modulo"]
        p_total = n_pcs * sku["kw_pcs"]
        if e_total >= energia and p_total >= potencia:
            candidatos.append({
                "sku": sku["sku"],
                "n_modulos_energia": n_modulos_e,
                "n_pcs": n_pcs,
                "e_total_kwh": e_total,
                "p_total_kw": p_total,
                "overhead_energia_pct": round((e_total - energia) / energia * 100, 1),
            })
    if not candidatos:
        return {"sku_recomendado": None, "candidatos": [], "obs": "Nenhum SKU Huawei na faixa cabe nesse sizing."}
    # Ordena por: menos cabinets totais, depois menor overhead.
    candidatos.sort(key=lambda c: (c["n_modulos_energia"] + c["n_pcs"], c["overhead_energia_pct"]))
    return {
        "sku_recomendado": candidatos[0],
        "candidatos": candidatos,
    }


# ===========================================================================
# Tool 9: monte_carlo_financeiro (Sprint 4-C)
# ===========================================================================

DEF_MONTE_CARLO_FINANCEIRO = {
    "name": "monte_carlo_financeiro",
    "description": (
        "Simulacao Monte Carlo do VPL (10.000 iteracoes default) para analise "
        "probabilistica do projeto. Substitui o tornado +-20% por uma analise "
        "robusta com distribuicoes triangulares (CAPEX/OPEX/Economia) e normal "
        "truncada (WACC). Devolve P10/P50/P90 do VPL e P(VPL > 0). "
        "USE quando o tornado de analisar_financeiro indicar incerteza alta "
        "(VPL central proximo de zero) OU quando o usuario explicitamente "
        "pedir analise de risco probabilistica."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "capex_brl": {"type": "number"},
            "opex_anual_brl": {"type": "number"},
            "economia_anual_brl": {"type": "number"},
            "horizonte_anos": {"type": "integer", "default": 20},
            "wacc_central": {"type": "number", "default": 0.12},
            "wacc_desvio_padrao": {
                "type": "number", "default": 0.02,
                "description": "Desvio-padrao da WACC (default 2 p.p.).",
            },
            "n_iteracoes": {"type": "integer", "default": 10000},
            "seed": {
                "type": "integer", "default": 42,
                "description": "Seed para reprodutibilidade (default 42).",
            },
        },
        "required": ["capex_brl", "opex_anual_brl", "economia_anual_brl"],
    },
}


# ===========================================================================
# Tool 10: consultar_base_regulatoria (Sprint 4-B)
# ===========================================================================

DEF_CONSULTAR_BASE_REGULATORIA = {
    "name": "consultar_base_regulatoria",
    "description": (
        "Consulta a base regulatoria indexada (REN ANEEL 1.000/2021, Lei "
        "14.300/2022, NBR 13534, REH ANEEL 3.477/2025) via retrieval BM25. "
        "USE SEMPRE antes de citar artigo especifico, valor de tarifa ou "
        "regra normativa: o LLM nao deve inventar numeros de artigos ou "
        "tarifas. Retorna ate 3 chunks relevantes com fonte e score. Se "
        "nenhum chunk for retornado, informe ao usuario que a regra "
        "consultada nao esta no corpus indexado."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Pergunta ou termo em PT-BR. Ex: 'multa de ultrapassagem "
                    "de demanda', 'hospital UTI autonomia minima', 'Lei "
                    "14.300 transicao TUSD'."
                ),
            },
            "top_k": {
                "type": "integer", "default": 3,
                "description": "Numero de chunks a retornar (1-5).",
            },
        },
        "required": ["query"],
    },
}


def exec_consultar_base_regulatoria(args: dict) -> dict:
    # Import tardio para nao quebrar caso rank_bm25/pypdf nao instalados
    from rag import consultar_regulamento

    top_k = max(1, min(5, args.get("top_k", 3)))
    resultados = consultar_regulamento(
        query=args["query"],
        top_k=top_k,
    )
    if not resultados:
        return {
            "encontrados": 0,
            "obs": (
                "Nenhum chunk relevante encontrado na base regulatoria "
                "indexada. Informe ao usuario que esta regra/artigo nao "
                "esta disponivel no corpus atual."
            ),
            "chunks": [],
        }
    return {
        "encontrados": len(resultados),
        "chunks": [
            {
                "fonte": r.fonte,
                "chunk_id": r.chunk_id,
                "score": round(r.score, 2),
                # Trunca para nao explodir contexto do LLM (max 1500 chars)
                "texto": r.texto[:1500] + ("..." if len(r.texto) > 1500 else ""),
            }
            for r in resultados
        ],
    }


def _classificar_risco(prob_viavel: float) -> str:
    """Mapeia P(VPL>0) em rotulo verbal para o LLM."""
    if prob_viavel >= 0.80:
        return "BAIXO (projeto provavelmente viavel)"
    if prob_viavel >= 0.50:
        return "MEDIO (viabilidade incerta - depende de cotacao real)"
    if prob_viavel >= 0.20:
        return "ALTO (viabilidade improvavel sem revenue stacking)"
    return "MUITO ALTO (projeto inviavel pelas premissas atuais)"


def exec_monte_carlo_financeiro(args: dict) -> dict:
    r = simulacao_monte_carlo(
        capex_brl=args["capex_brl"],
        opex_anual_brl=args["opex_anual_brl"],
        economia_anual_brl=args["economia_anual_brl"],
        horizonte_anos=args.get("horizonte_anos", 20),
        wacc_central=args.get("wacc_central", 0.12),
        wacc_desvio_padrao=args.get("wacc_desvio_padrao", 0.02),
        n_iteracoes=args.get("n_iteracoes", 10_000),
        seed=args.get("seed", 42),
    )
    p50 = r.vpl_brl_p50
    p10 = r.vpl_brl_p10
    p90 = r.vpl_brl_p90
    spread_relativo = None
    if p50 != 0:
        spread_relativo = round((p90 - p10) / abs(p50), 2)

    return {
        "n_iteracoes": r.n_iteracoes,
        "vpl_brl_p10": round(p10, 0),
        "vpl_brl_p25": round(r.vpl_brl_p25, 0),
        "vpl_brl_p50": round(p50, 0),
        "vpl_brl_p75": round(r.vpl_brl_p75, 0),
        "vpl_brl_p90": round(p90, 0),
        "vpl_brl_media": round(r.vpl_brl_media, 0),
        "vpl_brl_desvio_padrao": round(r.vpl_brl_desvio_padrao, 0),
        "vpl_brl_min_observado": round(r.vpl_brl_min, 0),
        "vpl_brl_max_observado": round(r.vpl_brl_max, 0),
        "probabilidade_viavel_pct": round(r.probabilidade_viavel * 100, 1),
        "spread_p10_p90_relativo": spread_relativo,
        "classificacao_risco": _classificar_risco(r.probabilidade_viavel),
        "premissas_distribuicoes": r.distribuicoes_usadas,
        # NAO retorna histograma para o LLM (50+ valores) -- so a estatistica.
        "histograma_n_bins": len(r.histograma_contagens),
    }


# ===========================================================================
# Registry
# ===========================================================================

TOOL_DEFINITIONS = [
    DEF_GERAR_PERFIL_INDUSTRIAL,
    DEF_DIMENSIONAR_PEAK_SHAVING,
    DEF_DIMENSIONAR_ARBITRAGEM,
    DEF_DIMENSIONAR_BACKUP,
    DEF_SIMULAR_DESPACHO,
    DEF_ANALISAR_FINANCEIRO,
    DEF_CALCULAR_SOH,
    DEF_MATCH_SKU_HUAWEI,
    DEF_MONTE_CARLO_FINANCEIRO,
    DEF_CONSULTAR_BASE_REGULATORIA,
]


TOOL_EXECUTORS = {
    "gerar_perfil_industrial":   exec_gerar_perfil_industrial,
    "dimensionar_peak_shaving":  exec_dimensionar_peak_shaving,
    "dimensionar_arbitragem":    exec_dimensionar_arbitragem,
    "dimensionar_backup":        exec_dimensionar_backup,
    "simular_despacho":          exec_simular_despacho,
    "analisar_financeiro":       exec_analisar_financeiro,
    "calcular_soh":              exec_calcular_soh,
    "match_sku_huawei":          exec_match_sku_huawei,
    "monte_carlo_financeiro":    exec_monte_carlo_financeiro,
    "consultar_base_regulatoria": exec_consultar_base_regulatoria,
}


def executar_tool(nome: str, args: dict) -> dict:
    """Executa uma tool por nome. Captura ValueError e devolve como dict."""
    if nome not in TOOL_EXECUTORS:
        return {"erro": f"Tool '{nome}' nao registrada."}
    try:
        return TOOL_EXECUTORS[nome](args)
    except ValueError as e:
        return {"erro": str(e)}
    except Exception as e:
        return {"erro": f"{type(e).__name__}: {e}"}
