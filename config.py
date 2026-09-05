# config.py
# Configuração central das atividades do evento.
# Para adicionar/remover uma atividade no futuro, basta editar este dicionário —
# o restante do app (formulário, validação, planilha) se adapta automaticamente.
#
# preco_unitario: para atividades com treino/competição (has_mode=True), é um
# dicionário {"Treino": valor, "Competição": valor} — os preços podem ser
# diferentes por modo. Para as demais (modo fixo), é só um número. Se algum
# dia faltar um preço, deixe None nesse lugar — a planilha registra a compra
# normalmente, só sem valor_unitario/valor_total preenchidos naquela linha.

ACTIVITIES = {
    "arco_flecha": {
        "label": "Arco e Flecha",
        "has_mode": True,       # tem treino/competição
        "fixed_mode": None,
        "collects_competitor_names": True,  # nome, telefone e clã do(s) competidor(es) quando em modo competição
        "preco_unitario": {"Treino": 20.00, "Competição": 30.00},
        "sheet_name": "arco_flecha",  # aba na planilha mestra que recebe os competidores
        "num_tiros": 4,          # quadrados de nota na tela de Competições
        "icon": "🏹",
    },
    "arremesso_machado": {
        "label": "Arremesso de Machado",
        "has_mode": True,
        "fixed_mode": None,
        "collects_competitor_names": True,
        "preco_unitario": {"Treino": 10.00, "Competição": 20.00},
        "sheet_name": "machado",
        "num_tiros": 3,
        "icon": "🪓",
    },
    "swordplay": {
        "label": "Swordplay",
        "has_mode": True,
        "fixed_mode": None,
        "collects_competitor_names": True,
        "preco_unitario": {"Treino": 10.00, "Competição": 20.00},
        "sheet_name": "swordplay",
        "num_tiros": None,      # não pontua por tiros — usa posição final no ranking
        "icon": "⚔️",
    },
    "vestimenta": {
        "label": "Vestimenta",
        "has_mode": False,
        "fixed_mode": "Competição",  # sempre competição, sem opção de treino
        "collects_competitor_names": True,
        "collects_cla": False,  # culturais não usam clã — só nome e telefone
        "preco_unitario": 20.00,
        "sheet_name": "vestimenta",
        "icon": "👗",
    },
    "bardos": {
        "label": "Bardos",
        "has_mode": False,
        "fixed_mode": "Competição",
        "collects_competitor_names": True,
        "collects_cla": False,
        "preco_unitario": 20.00,
        "sheet_name": "bardos",
        "icon": "🎻",
    },
    "feiticos": {
        "label": "Feitiços",
        "has_mode": False,
        "fixed_mode": "Competição",
        "collects_competitor_names": True,
        "collects_cla": False,
        "preco_unitario": 20.00,
        "sheet_name": "feiticos",
        "icon": "🪄",
    },
    # "cacaAoTesouro" fica de fora por enquanto (ainda incerto).
    # Quando confirmado, basta adicionar aqui:
    # "caca_tesouro": {
    #     "label": "Desafio de Caça ao Tesouro",
    #     "has_mode": False,
    #     "fixed_mode": "Competição",
    #     "collects_competitor_names": False,
    #     "preco_unitario": None,
    #     "sheet_name": "caca_tesouro",
    # },
}

# As 3 atividades físicas de torneio, na ordem em que aparecem nas telas de
# Competições/Resultados. Culturais ficam à parte (TORNEIO_CULTURAIS abaixo).
TORNEIO_FISICOS = ["arco_flecha", "arremesso_machado", "swordplay"]
TORNEIO_CULTURAIS = ["vestimenta", "bardos", "feiticos"]

MODE_OPTIONS = ["Treino", "Competição"]
PAYMENT_OPTIONS = ["PIX", "Dinheiro"]

# Aba principal (a mesma de sempre) e cabeçalhos das abas de cada atividade.
NOME_ABA_AQUISICAO = "aquisicao"
COMPETITOR_SHEET_HEADERS = ["nome", "cla", "telefone"]  # físicas, antes de pontuar/posicionar
CULTURAL_SHEET_HEADERS = ["nome", "telefone"]           # culturais — sem clã
SWORDPLAY_HEADERS = ["nome", "cla", "telefone", "posicao"]


def score_headers(num_tiros):
    """Cabeçalho da aba de uma atividade pontuada por tiros (Arco/Machado):
    nome/clã/telefone + um "tiroN" por tentativa + total."""
    tiros = [f"tiro{i}" for i in range(1, num_tiros + 1)]
    return ["nome", "cla", "telefone"] + tiros + ["total"]


def sheet_headers_for(key, cfg):
    """Cabeçalho correto da aba de UMA atividade, seja pra alimentar (a
    partir da Aquisição) ou pra ler nas telas de Competições/Resultados —
    usar sempre esta função garante que todo mundo concorda no mesmo
    cabeçalho, sem risco de uma tela reescrever com um formato diferente
    do que outra espera."""
    if key == "swordplay":
        return SWORDPLAY_HEADERS
    if cfg.get("num_tiros"):
        return score_headers(cfg["num_tiros"])
    if cfg.get("collects_cla", True):
        return COMPETITOR_SHEET_HEADERS
    return CULTURAL_SHEET_HEADERS

# Colunas da planilha Google Sheets, nesta ordem
SHEET_HEADERS = [
    "id_compra",
    "data_hora",
    "atividade",
    "modo",              # treino/competição
    "quantidade",        # unidades/ingressos comprados
    "valor_unitario",    # vazio até o preço ser definido em config.py
    "valor_total",       # quantidade × valor_unitario
    "forma_pagamento",   # PIX ou Dinheiro
    "nome_competidor",   # vazio quando não aplicável; uma linha por competidor
    "telefone_competidor", # com DDD; vazio quando não aplicável
    "cla_competidor",    # vazio quando não aplicável
    "link_foto",
    "responsavel_nome",   # vem do login com Google, não é mais texto livre
    "responsavel_email",
]
