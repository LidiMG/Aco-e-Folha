"""Testes do Aço & Folha (v3). Cada teste descreve, no nome, o que garante."""
import io
import json
from datetime import datetime, timedelta, timezone

import requests
from gspread.exceptions import APIError

from conftest import aplicativo, foto_jpeg

ACTIVITIES = aplicativo.ACTIVITIES


# ---------------------------------------------------------------------------
# Ajudantes
# ---------------------------------------------------------------------------

def preencher(planilha, key, linhas):
    """Coloca o cabeçalho certo e as linhas dadas na aba da atividade."""
    cfg = ACTIVITIES[key]
    cabecalho = aplicativo.sheet_headers_for(key, cfg)
    aba = planilha.aba(cfg["sheet_name"])
    aba.dados = [list(cabecalho)] + [[l.get(c, "") for c in cabecalho] for l in linhas]
    return aba


def comprar(cliente, itens, forma="Dinheiro", pid="abcd1234", total=None):
    if total is None:
        total = aplicativo.calcular_total([dict(i) for i in itens])
    return cliente.post("/submit", data={
        "forma_pagamento": forma,
        "purchase_id": pid,
        "total_exibido": f"{total:.2f}",
        "activities_json": json.dumps(itens),
    })


def competidor(nome, telefone="51999998888", cla=""):
    return {"nome": nome, "telefone": telefone, "cla": cla}


def pontuar(cliente, key, linha, tiros, id_inscricao="", nome="", foto=None):
    return cliente.post(f"/competicoes/{key}/pontuar", data={
        "row": str(linha), "id_inscricao": id_inscricao, "nome": nome,
        "tiros": json.dumps(tiros),
        "foto_alvo": (io.BytesIO(foto if foto is not None else foto_jpeg()), "alvo.jpg", "image/jpeg"),
    }, content_type="multipart/form-data")


def erro_do_sheets(status):
    resposta = requests.Response()
    resposta.status_code = status
    resposta._content = json.dumps({"error": {"code": status, "message": "x", "status": "X"}}).encode()
    return APIError(resposta)


# ---------------------------------------------------------------------------
# Item 2 — novas tentativas automáticas
# ---------------------------------------------------------------------------

def test_erro_429_da_planilha_e_reconhecido_e_tentado_de_novo(planilha):
    assert aplicativo._status_http(erro_do_sheets(429)) == 429
    chamadas = {"n": 0}

    def instavel():
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise erro_do_sheets(503)
        return "ok"

    assert aplicativo.tentar_google(instavel) == "ok"
    assert chamadas["n"] == 3


def test_mensagem_de_limite_do_google_aparece_para_429():
    assert "muitos envios" in aplicativo.mensagem_amigavel(erro_do_sheets(429), "gravar")


# ---------------------------------------------------------------------------
# Itens 1 e 9 — código da equipe, organização e administração
# ---------------------------------------------------------------------------

def test_competicoes_pede_o_codigo_da_equipe(planilha, anonimo):
    resposta = anonimo.get("/competicoes")
    assert resposta.status_code == 302 and "/entrar-equipe" in resposta.headers["Location"]
    assert anonimo.post("/competicoes/swordplay/posicao", json={"posicoes": []}).status_code == 403


def test_codigo_certo_libera_e_errado_nao(planilha, anonimo):
    errado = anonimo.post("/entrar-equipe", data={"codigo": "0000", "next": "/competicoes"})
    assert "Código incorreto" in errado.get_data(as_text=True)
    certo = anonimo.post("/entrar-equipe", data={"codigo": "4321", "next": "/competicoes"})
    assert certo.status_code == 302 and certo.headers["Location"].endswith("/competicoes")
    assert anonimo.get("/competicoes").status_code == 200


def test_muitas_tentativas_erradas_bloqueiam_o_codigo(planilha, anonimo):
    for _ in range(5):
        anonimo.post("/entrar-equipe", data={"codigo": "1111"})
    bloqueado = anonimo.post("/entrar-equipe", data={"codigo": "4321"})
    assert "Espere 10 minutos" in bloqueado.get_data(as_text=True)


def test_codigo_sobrevive_ao_login_google_e_ao_sair(planilha, anonimo):
    anonimo.post("/entrar-equipe", data={"codigo": "4321"})
    # O retorno do Google chega sem os cookies da sessão: a sessão é refeita.
    with anonimo.session_transaction() as s:
        s.clear()
        s["user_email"] = "atendente@exemplo.com"
    assert anonimo.get("/aquisicao").status_code == 200
    anonimo.get("/logout")
    assert anonimo.get("/competicoes").status_code == 200


def test_resultados_continua_aberto(planilha, anonimo):
    assert anonimo.get("/resultados").status_code == 200
    assert anonimo.get("/resultados/arco_flecha").status_code == 200


def test_aquisicao_pede_login_google_e_codigo(planilha):
    so_login = aplicativo.app.test_client()
    with so_login.session_transaction() as s:
        s["user_email"] = "alguem@exemplo.com"
    resposta = so_login.get("/aquisicao")
    assert resposta.status_code == 302 and "/entrar-equipe" in resposta.headers["Location"]


def test_organizacao_entra_sem_codigo(planilha, organizacao):
    assert organizacao.get("/competicoes").status_code == 200


def test_administracao_e_so_para_o_email_da_administracao(planilha, equipe, organizacao, administracao):
    assert equipe.get("/administracao").status_code == 403
    assert organizacao.get("/administracao").status_code == 403
    assert administracao.get("/administracao").status_code == 200
    assert "Administração" in administracao.get("/").get_data(as_text=True)
    assert "/administracao" not in equipe.get("/").get_data(as_text=True)


# ---------------------------------------------------------------------------
# Item 1 — nota máxima
# ---------------------------------------------------------------------------

def test_nota_acima_de_10_e_recusada(planilha, drive, equipe):
    preencher(planilha, "arco_flecha", [{"nome": "Davi", "id_inscricao": "aa000001-1"}])
    resposta = pontuar(equipe, "arco_flecha", 2, [999, 10, 10, 10], "aa000001-1", "Davi")
    assert resposta.status_code == 400 and "de 0 a 10" in resposta.get_json()["errors"][0]
    assert pontuar(equipe, "arco_flecha", 2, [10, 9, 8, 7], "aa000001-1", "Davi").get_json()["ok"]


# ---------------------------------------------------------------------------
# Item 3 — a nota vai para a pessoa certa
# ---------------------------------------------------------------------------

def test_nota_vai_para_a_pessoa_certa_mesmo_com_a_planilha_reordenada(planilha, drive, equipe):
    aba = preencher(planilha, "arco_flecha", [
        {"nome": "Zeca", "id_inscricao": "aa000001-1"},
        {"nome": "Bia", "id_inscricao": "aa000002-1"},
    ])
    # A tela foi aberta com a Bia na linha 3; alguém ordenou a aba de A a Z.
    aba.dados[1:] = sorted(aba.dados[1:], key=lambda l: l[0])
    assert pontuar(equipe, "arco_flecha", 3, [8, 9, 10, 7], "aa000002-1", "Bia").get_json()["ok"]
    totais = {l["nome"]: l["total"] for l in aba.linhas()}
    assert totais == {"Bia": 34, "Zeca": ""}


def test_linha_sem_codigo_so_aceita_se_o_nome_bater(planilha, drive, equipe):
    preencher(planilha, "arco_flecha", [{"nome": "Ana"}, {"nome": "Bruno"}])
    resposta = pontuar(equipe, "arco_flecha", 2, [1, 1, 1, 1], "", "Bruno")
    assert resposta.status_code == 409


def test_reenvio_da_mesma_nota_nao_da_erro(planilha, drive, equipe):
    preencher(planilha, "arremesso_machado", [{"nome": "Eva", "id_inscricao": "aa000003-1"}])
    assert pontuar(equipe, "arremesso_machado", 2, [5, 6, 7], "aa000003-1", "Eva").get_json()["ok"]
    de_novo = pontuar(equipe, "arremesso_machado", 2, [5, 6, 7], "aa000003-1", "Eva").get_json()
    assert de_novo["ok"] and de_novo.get("ja_salva")
    outra = pontuar(equipe, "arremesso_machado", 2, [1, 1, 1], "aa000003-1", "Eva")
    assert outra.status_code == 409


# ---------------------------------------------------------------------------
# Item 4 — posições
# ---------------------------------------------------------------------------

def _ranking(planilha):
    return preencher(planilha, "swordplay", [
        {"nome": "Ana", "posicao": 1, "id_inscricao": "s1-1"},
        {"nome": "Bruno", "posicao": 2, "id_inscricao": "s2-1"},
        {"nome": "Carla", "posicao": 3, "id_inscricao": "s3-1"},
    ])


def _posicoes(aba):
    return {l["nome"]: l["posicao"] for l in aba.linhas()}


def test_trocar_primeiro_com_segundo_funciona(planilha, equipe):
    aba = _ranking(planilha)
    resposta = equipe.post("/competicoes/swordplay/posicao", json={"posicoes": [
        {"row": 2, "id_inscricao": "s1-1", "nome": "Ana", "posicao": "2"},
        {"row": 3, "id_inscricao": "s2-1", "nome": "Bruno", "posicao": "1"},
    ]})
    assert resposta.get_json()["ok"]
    assert _posicoes(aba) == {"Ana": 2, "Bruno": 1, "Carla": 3}


def test_reordenar_varios_numa_vez_e_uma_chamada_so(planilha, equipe):
    aba = _ranking(planilha)
    gravacoes_antes = aba.gravacoes
    equipe.post("/competicoes/swordplay/posicao", json={"posicoes": [
        {"row": 2, "id_inscricao": "s1-1", "nome": "Ana", "posicao": "3"},
        {"row": 3, "id_inscricao": "s2-1", "nome": "Bruno", "posicao": "1"},
        {"row": 4, "id_inscricao": "s3-1", "nome": "Carla", "posicao": "2"},
    ]})
    assert _posicoes(aba) == {"Ana": 3, "Bruno": 1, "Carla": 2}
    assert aba.gravacoes - gravacoes_antes == 1


def test_posicao_repetida_no_resultado_final_nao_grava_nada(planilha, equipe):
    aba = _ranking(planilha)
    resposta = equipe.post("/competicoes/swordplay/posicao", json={"posicoes": [
        {"row": 4, "id_inscricao": "s3-1", "nome": "Carla", "posicao": "1"},
    ]})
    assert resposta.status_code == 400
    assert "Ana e Carla" in resposta.get_json()["errors"][0]
    assert _posicoes(aba) == {"Ana": 1, "Bruno": 2, "Carla": 3}


def test_apagar_uma_posicao(planilha, equipe):
    aba = _ranking(planilha)
    equipe.post("/competicoes/swordplay/posicao", json={"posicoes": [
        {"row": 4, "id_inscricao": "s3-1", "nome": "Carla", "posicao": ""},
    ]})
    assert _posicoes(aba)["Carla"] == ""


# ---------------------------------------------------------------------------
# Item 5 — fotos e tamanho
# ---------------------------------------------------------------------------

def test_arquivo_que_nao_e_foto_e_recusado(planilha, drive, equipe):
    aba = preencher(planilha, "arco_flecha", [{"nome": "Eva", "id_inscricao": "aa000004-1"}])
    html = b"<html><script>alert(1)</script></html>"
    resposta = pontuar(equipe, "arco_flecha", 2, [1, 2, 3, 4], "aa000004-1", "Eva", foto=html)
    assert resposta.status_code == 400 and "não é uma foto" in resposta.get_json()["errors"][0]
    assert aba.linhas()[0]["total"] == ""


def test_envio_grande_demais_e_recusado(planilha, equipe):
    grande = b"0" * (aplicativo.MAX_UPLOAD_MB * 1024 * 1024 + 10)
    resposta = equipe.post("/competicoes/arco_flecha/pontuar", data={
        "row": "2", "tiros": "[1,1,1,1]", "foto_alvo": (io.BytesIO(grande), "a.jpg", "image/jpeg"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 413 and resposta.get_json()["ok"] is False


def test_rota_de_fotos_so_entrega_imagens(planilha, monkeypatch, anonimo):
    class Pedido:
        def __init__(self, resultado):
            self.resultado = resultado

        def execute(self):
            return self.resultado

    class Arquivos:
        def get(self, fileId, fields):
            tipo = "text/html" if fileId.startswith("html") else "image/jpeg"
            return Pedido({"parents": ["pastaAlvos"], "mimeType": tipo})

        def get_media(self, fileId):
            return Pedido(b"conteudo")

    class Servico:
        def files(self):
            return Arquivos()

    monkeypatch.setattr(aplicativo, "get_drive_service", lambda: Servico())
    aplicativo._fotos_em_cache.clear()
    assert anonimo.get("/resultados/foto/htmlABCDEFGHIJ").status_code == 404
    imagem = anonimo.get("/resultados/foto/jpegABCDEFGHIJ")
    assert imagem.status_code == 200 and imagem.headers["X-Content-Type-Options"] == "nosniff"


# ---------------------------------------------------------------------------
# Itens 6, 10, 12, 13 e 15 — compra
# ---------------------------------------------------------------------------

def test_compra_grava_horario_de_brasilia_e_codigo_de_inscricao(planilha, equipe):
    resposta = comprar(equipe, [
        {"activity": "arco_flecha", "modo": "Competição", "quantidade": 2,
         "competidores": [competidor("Ana", cla="Lobo"), competidor("Bia")]},
        {"activity": "arco_flecha", "modo": "Treino", "quantidade": 3},
    ])
    assert resposta.get_json()["ok"]
    linhas = planilha.aba("aquisicao").linhas()
    assert [l["id_inscricao"] for l in linhas] == ["abcd1234-1", "abcd1234-2", ""]
    assert [l["valor_total"] for l in linhas] == [30.0, 30.0, 60.0]
    gravado = datetime.strptime(linhas[0]["data_hora"], "%Y-%m-%d %H:%M:%S")
    brasilia = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    assert abs((gravado - brasilia).total_seconds()) < 120
    # A cópia para a aba da atividade leva o mesmo código de inscrição.
    aba = planilha.aba("arco_flecha").linhas()
    assert [(l["nome"], l["id_inscricao"]) for l in aba] == [("Ana", "abcd1234-1"), ("Bia", "abcd1234-2")]


def test_preco_diferente_do_que_a_tela_mostrava_e_recusado(planilha, equipe):
    resposta = comprar(equipe, [{"activity": "beberrao", "quantidade": 1, "competidores": [competidor("Ana")]}],
                       total=20.0)
    dados = resposta.get_json()
    assert resposta.status_code == 409 and dados["precos_mudaram"]
    assert planilha.aba("aquisicao").linhas() == []


def test_mesma_compra_reenviada_nao_duplica(planilha, equipe):
    itens = [{"activity": "beberrao", "quantidade": 1, "competidores": [competidor("Ana")]}]
    assert comprar(equipe, itens).get_json()["ok"]
    de_novo = comprar(equipe, itens).get_json()
    assert de_novo["ok"] and de_novo["ja_registrada"]
    assert len(planilha.aba("aquisicao").linhas()) == 1


def test_mesmo_codigo_com_outra_compra_avisa_em_vez_de_perder(planilha, equipe):
    comprar(equipe, [{"activity": "beberrao", "quantidade": 1, "competidores": [competidor("Ana")]}])
    outra = comprar(equipe, [{"activity": "beberrao", "quantidade": 1, "competidores": [competidor("Outra Pessoa")]}])
    assert outra.status_code == 409 and outra.get_json()["conteudo_diferente"]


def test_envio_que_demora_demais_nao_grava(planilha, equipe, monkeypatch):
    monkeypatch.setattr(aplicativo, "PRAZO_PARA_GRAVAR_S", -1)
    resposta = comprar(equipe, [{"activity": "arremesso_machado", "modo": "Treino", "quantidade": 1}])
    assert resposta.status_code == 503
    assert planilha.aba("aquisicao").linhas() == []


def test_copia_para_a_aba_nao_duplica_inscritos(planilha):
    inscricao = [{"id_inscricao": "x1-1", "nome": "Ana", "telefone": "51999998888", "cla": ""}]
    aplicativo.garantir_inscritos("swordplay", inscricao)
    aplicativo.garantir_inscritos("swordplay", inscricao)
    assert len(planilha.aba("swordplay").linhas()) == 1


# ---------------------------------------------------------------------------
# Item 11 — conferência automática
# ---------------------------------------------------------------------------

def test_lista_do_instrutor_completa_quem_faltou(planilha, equipe, monkeypatch):
    # Simula a cópia perdida (ex.: reinício do Render logo depois da compra).
    monkeypatch.setattr(aplicativo, "em_segundo_plano", lambda funcao, *args: None)
    comprar(equipe, [{"activity": "swordplay", "modo": "Competição", "quantidade": 1,
                      "competidores": [competidor("Duda")]}])
    assert planilha.aba("swordplay").dados == []
    pagina = equipe.get("/competicoes/swordplay").get_data(as_text=True)
    assert "Duda" in pagina
    assert [l["nome"] for l in planilha.aba("swordplay").linhas()] == ["Duda"]


# ---------------------------------------------------------------------------
# Item 14 — empates e desempate
# ---------------------------------------------------------------------------

def _arco_com_empate(planilha):
    return preencher(planilha, "arco_flecha", [
        {"nome": "Ana", "total": 40, "id_inscricao": "e1-1"},
        {"nome": "Bia", "total": 35, "id_inscricao": "e2-1"},
        {"nome": "Caio", "total": 30, "id_inscricao": "e3-1"},
        {"nome": "Duda", "total": 30, "id_inscricao": "e4-1"},
        {"nome": "Enzo", "total": 10, "id_inscricao": "e5-1"},
    ])


def test_empate_no_terceiro_lugar_mostra_os_dois(planilha, anonimo):
    _arco_com_empate(planilha)
    pagina = anonimo.get("/resultados/arco_flecha").get_data(as_text=True)
    assert "Caio" in pagina and "Duda" in pagina and "Enzo" not in pagina
    assert pagina.count("aguardando desempate") == 2


def test_organizacao_registra_desempate_e_equipe_nao(planilha, equipe, organizacao, anonimo):
    aba = _arco_com_empate(planilha)
    itens = [{"row": 5, "id_inscricao": "e4-1", "nome": "Duda", "ordem": 1},
             {"row": 4, "id_inscricao": "e3-1", "nome": "Caio", "ordem": 2}]
    assert equipe.post("/competicoes/arco_flecha/desempate", json={"itens": itens}).status_code == 403
    assert organizacao.post("/competicoes/arco_flecha/desempate", json={"itens": itens}).get_json()["ok"]
    assert {l["nome"]: l["desempate"] for l in aba.linhas()}["Duda"] == 1
    pagina = anonimo.get("/resultados/arco_flecha").get_data(as_text=True)
    assert "Duda" in pagina and "Caio" not in pagina and "decidido no desempate" in pagina


def test_desempate_fica_em_resultados_e_so_para_a_organizacao(planilha, anonimo, equipe, organizacao):
    _arco_com_empate(planilha)
    assert "Salvar desempate" not in anonimo.get("/resultados/arco_flecha").get_data(as_text=True)
    assert "Salvar desempate" not in equipe.get("/resultados/arco_flecha").get_data(as_text=True)
    assert "Salvar desempate" not in organizacao.get("/competicoes/arco_flecha").get_data(as_text=True)
    assert "Salvar desempate" in organizacao.get("/resultados/arco_flecha").get_data(as_text=True)


def test_desempate_resolvido_continua_editavel_com_quem_ficou_em_4o(planilha, organizacao):
    aba = _arco_com_empate(planilha)
    for linha in aba.dados[1:]:
        if linha[0] in ("Caio", "Duda"):
            linha[aba.coluna("desempate")] = 1 if linha[0] == "Duda" else 2
    pagina = organizacao.get("/resultados/arco_flecha").get_data(as_text=True)
    secao = pagina[pagina.index("Desempate</h2>"):]
    assert "Caio" in secao and "Duda" in secao


def test_podio_por_posicao_mostra_a_definir(planilha, anonimo):
    preencher(planilha, "vestimenta", [{"nome": "Lia", "posicao": 3, "id_inscricao": "v1-1"}])
    pagina = anonimo.get("/resultados/vestimenta").get_data(as_text=True)
    assert pagina.count("A definir") == 2 and "Lia" in pagina


def test_resultados_ficam_30_segundos_em_memoria(planilha, anonimo):
    aba = _arco_com_empate(planilha)
    anonimo.get("/resultados/arco_flecha")
    leituras = aba.leituras
    anonimo.get("/resultados/arco_flecha")
    assert aba.leituras == leituras


# ---------------------------------------------------------------------------
# Correção de nota (organização)
# ---------------------------------------------------------------------------

def test_organizacao_corrige_e_limpa_nota(planilha, equipe, organizacao):
    aba = preencher(planilha, "arco_flecha", [{"nome": "Ana", "tiro1": 1, "tiro2": 1, "tiro3": 1, "tiro4": 1,
                                                "total": 4, "foto_alvo": "link", "id_inscricao": "c1-1"}])
    corpo = {"acao": "corrigir", "row": 2, "id_inscricao": "c1-1", "nome": "Ana", "tiros": [9, 9, 9, 9]}
    assert equipe.post("/competicoes/arco_flecha/corrigir", json=corpo).status_code == 403
    assert organizacao.post("/competicoes/arco_flecha/corrigir", json=corpo).get_json()["ok"]
    linha = aba.linhas()[0]
    assert (linha["total"], linha["foto_alvo"], linha["alterado_por"]) == (36, "link", "org@exemplo.com")
    organizacao.post("/competicoes/arco_flecha/corrigir", json=dict(corpo, acao="limpar"))
    linha = aba.linhas()[0]
    assert (linha["total"], linha["foto_alvo"]) == ("", "")


# ---------------------------------------------------------------------------
# Administração — trocas, arquivo e resumo
# ---------------------------------------------------------------------------

def trocar(cliente, dados, foto=None):
    corpo = {"dados": json.dumps(dados)}
    if foto is not None:
        corpo["foto"] = (io.BytesIO(foto), "comprovante.jpg", "image/jpeg")
    return cliente.post("/administracao/troca", data=corpo, content_type="multipart/form-data")


def test_troca_no_treino_com_diferenca_e_comprovante(planilha, administracao, equipe, drive):
    comprar(equipe, [{"activity": "arremesso_machado", "modo": "Treino", "quantidade": 1}])
    dados = {"id_troca": "77777777", "sai": {"atividade": "arremesso_machado", "modo": "Treino"},
             "entra": {"atividade": "arco_flecha", "modo": "Treino"}, "forma_diferenca": "PIX"}
    assert trocar(administracao, dados, foto=foto_jpeg()).get_json()["ok"]
    linhas = planilha.aba("aquisicao").linhas()[1:]
    assert [(l["atividade"], l["quantidade"], l["valor_total"], l["forma_pagamento"]) for l in linhas] == [
        ("Arremesso de Machado", -1, -10.0, "Troca"),
        ("Arco e Flecha", 1, 10.0, "Troca"),
        ("Arco e Flecha", 0, 10.0, "PIX"),
    ]
    assert linhas[2]["link_foto"].startswith("https://drive.google.com/") and drive[0]["pasta"] == "pastaComprovantes"
    # Clicar de novo não registra outra troca.
    trocar(administracao, dados)
    assert len(planilha.aba("aquisicao").linhas()) == 4


def test_troca_no_treino_sem_compra_disponivel_e_recusada(planilha, administracao, equipe):
    comprar(equipe, [{"activity": "arremesso_machado", "modo": "Treino", "quantidade": 1}])
    dados = {"sai": {"atividade": "arremesso_machado", "modo": "Treino"},
             "entra": {"atividade": "swordplay", "modo": "Treino"}}
    assert trocar(administracao, dados).get_json()["ok"]
    segunda = trocar(administracao, dados)
    assert segunda.status_code == 400 and "disponível para trocar" in segunda.get_json()["errors"][0]
    sem_compra = trocar(administracao, {"sai": {"atividade": "swordplay", "modo": "Treino"},
                                        "entra": {"atividade": "arco_flecha", "modo": "Treino"},
                                        "forma_diferenca": "PIX"})
    # Swordplay Treino agora tem saldo 1 (veio da troca): essa pode.
    assert sem_compra.get_json()["ok"]


def test_troca_na_competicao_move_a_pessoa_de_lista(planilha, administracao, equipe):
    preencher(planilha, "swordplay", [{"nome": "Gil", "telefone": "51988887777", "id_inscricao": "g1-1"}])
    resposta = trocar(administracao, {
        "sai": {"atividade": "swordplay", "modo": "Competição", "row": 2, "id_inscricao": "g1-1", "nome": "Gil"},
        "entra": {"atividade": "rachar_lenha", "modo": "Competição", "nome": "Gil", "telefone": "51988887777"},
    })
    assert resposta.get_json()["ok"]
    assert planilha.aba("swordplay").linhas()[0]["situacao"] == "trocou"
    assert [l["nome"] for l in planilha.aba("rachar_lenha").linhas()] == ["Gil"]
    assert "Gil" not in equipe.get("/competicoes/swordplay").get_data(as_text=True)
    # E a conferência automática não traz a pessoa de volta para a lista antiga.
    assert "Gil" not in equipe.get("/competicoes/swordplay").get_data(as_text=True)


def test_quem_ja_competiu_nao_pode_trocar(planilha, administracao):
    preencher(planilha, "swordplay", [{"nome": "Gil", "posicao": 2, "id_inscricao": "g1-1"}])
    resposta = trocar(administracao, {
        "sai": {"atividade": "swordplay", "modo": "Competição", "row": 2, "id_inscricao": "g1-1", "nome": "Gil"},
        "entra": {"atividade": "swordplay", "modo": "Treino"},
    })
    assert resposta.status_code == 400 and "já tem resultado" in resposta.get_json()["errors"][0]


def test_preparar_para_arquivo_deixa_so_o_ddd(planilha, administracao):
    preencher(planilha, "swordplay", [{"nome": "Ana", "telefone": "(51) 99999-8888"},
                                      {"nome": "Bia", "telefone": 5511988887777}])
    assert administracao.post("/administracao/preparar-arquivo", json={"confirmacao": "nao"}).status_code == 400
    assert administracao.post("/administracao/preparar-arquivo", json={"confirmacao": "ARQUIVAR"}).get_json()["ok"]
    assert [l["telefone"] for l in planilha.aba("swordplay").linhas()] == ["51", "11"]


def test_aba_resumo_usa_o_separador_do_idioma_da_planilha(planilha, administracao):
    administracao.get("/administracao")
    resumo = planilha.aba("resumo").dados
    assert resumo[1] == ["Atividade", "Modo", "Quantidade", "Valor"]
    assert resumo[2][2].startswith('=SUMIFS(aquisicao!$E:$E;aquisicao!$C:$C;"Arco e Flecha"')
    assert any(l[0] == "PIX" and l[3].startswith('=SUMIF(aquisicao!$H:$H;"PIX"') for l in resumo)


def test_aba_resumo_troca_de_separador_se_o_google_der_erro(planilha, administracao, monkeypatch):
    # Idioma informado não bate com o da planilha: o app percebe o erro e corrige.
    monkeypatch.setattr(type(planilha), "locale", "en_US")
    administracao.get("/administracao")
    assert ";" in planilha.aba("resumo").dados[2][2]


def test_so_ddd():
    assert aplicativo.so_ddd("51999998888") == "51"
    assert aplicativo.so_ddd("+55 (11) 98888-7777") == "11"
    assert aplicativo.so_ddd(51999998888.0) == "51"
    assert aplicativo.so_ddd("51") == "51"
    assert aplicativo.so_ddd("") == ""


# ---------------------------------------------------------------------------
# Resumo do evento no app
# ---------------------------------------------------------------------------

def test_resumo_do_evento_soma_compras_e_trocas(planilha, equipe, organizacao, administracao):
    comprar(equipe, [{"activity": "arremesso_machado", "modo": "Treino", "quantidade": 2}], forma="PIX", pid="aaaa0001")
    comprar(equipe, [{"activity": "beberrao", "quantidade": 1, "competidores": [competidor("Ana")]}], pid="aaaa0002")
    trocar(administracao, {"sai": {"atividade": "arremesso_machado", "modo": "Treino"},
                           "entra": {"atividade": "arco_flecha", "modo": "Treino"}, "forma_diferenca": "Dinheiro"})
    aplicativo.esquecer_cache_aquisicao()
    dados = aplicativo.resumo_do_evento()
    por = {(a["atividade"], a["modo"]): (a["quantidade"], a["valor"]) for a in dados["atividades"]}
    assert por[("Arremesso de Machado", "Treino")] == (1, 10.0)
    assert por[("Arco e Flecha", "Treino")] == (1, 20.0)
    assert dados["por_forma"] == {"PIX": 20.0, "Dinheiro": 20.0}
    assert (dados["total"], dados["compras"], dados["trocas"]) == (40.0, 2, 1)
    assert organizacao.get("/administracao").status_code == 403
    assert "R$ 40,00" in administracao.get("/administracao").get_data(as_text=True)


def test_valor_da_planilha_entende_texto_em_reais():
    assert aplicativo._valor_da_planilha("R$ 1.234,50") == 1234.5
    assert aplicativo._valor_da_planilha("-R$ 10,00") == -10.0
    assert aplicativo._valor_da_planilha(30) == 30.0
    assert aplicativo._valor_da_planilha("") == 0.0
