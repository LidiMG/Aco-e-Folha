"""Planilha e Drive simulados para os testes (nada fala com o Google de verdade).

Como rodar, na pasta do projeto:
    pip install -r requirements-dev.txt
    python -m pytest
"""
import io
import os
import sys

import pytest

# As variáveis precisam existir ANTES de importar o app.
os.environ.update({
    "FLASK_SECRET_KEY": "chave-de-teste",
    "CODIGO_EQUIPE": "4321",
    "EMAIL_ORGANIZACAO": "org@exemplo.com",
    "EMAIL_ADMINISTRACAO": "adm@exemplo.com",
    "GOOGLE_DRIVE_FOLDER_ID": "pastaComprovantes",
    "GOOGLE_DRIVE_ALVOS_FOLDER_ID": "pastaAlvos",
})
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread  # noqa: E402
from gspread.utils import a1_range_to_grid_range  # noqa: E402
from PIL import Image  # noqa: E402

import app as aplicativo  # noqa: E402


def _texto(valor):
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


class AbaFalsa:
    """Imita o pedaço do gspread.Worksheet que o app usa. Conta as
    chamadas, para os testes conferirem quantas idas ao Google houve."""

    def __init__(self, titulo, linhas=()):
        self.title = titulo
        self.dados = [list(l) for l in linhas]
        self.leituras = 0
        self.gravacoes = 0

    # --- utilidades ---------------------------------------------------------
    def _garante(self, linha, coluna):
        while len(self.dados) < linha:
            self.dados.append([])
        while len(self.dados[linha - 1]) < coluna:
            self.dados[linha - 1].append("")

    @staticmethod
    def _como_planilha(valor, modo):
        # Com USER_ENTERED, o apóstrofo da frente só força texto e não fica gravado.
        if modo == "USER_ENTERED" and isinstance(valor, str) and valor.startswith("'"):
            return valor[1:]
        return valor

    def _escrever(self, faixa, valores, modo):
        if ":" not in faixa:
            faixa = f"{faixa}:{faixa}"
        g = a1_range_to_grid_range(faixa)
        r0, c0 = g.get("startRowIndex", 0) + 1, g.get("startColumnIndex", 0) + 1
        for i, linha in enumerate(valores):
            for j, v in enumerate(linha):
                self._garante(r0 + i, c0 + j)
                self.dados[r0 + i - 1][c0 + j - 1] = self._como_planilha(v, modo)

    def coluna(self, nome):
        return self.dados[0].index(nome)

    def linhas(self):
        """Linhas de dados como dicionários (para as conferências dos testes)."""
        if not self.dados:
            return []
        cab = self.dados[0]
        return [dict(zip(cab, l + [""] * (len(cab) - len(l)))) for l in self.dados[1:]]

    # --- API imitada --------------------------------------------------------
    def row_values(self, n):
        self.leituras += 1
        return [_texto(v) for v in self.dados[n - 1]] if n <= len(self.dados) else []

    def col_values(self, n):
        self.leituras += 1
        return [_texto(l[n - 1]) if len(l) >= n else "" for l in self.dados]

    def get_all_values(self, value_render_option=None):
        self.leituras += 1
        if value_render_option == "UNFORMATTED_VALUE":
            return [list(l) for l in self.dados]
        return [[_texto(v) for v in l] for l in self.dados]

    def batch_get(self, faixas):
        self.leituras += 1
        resultado = []
        for faixa in faixas:
            letra = faixa.split(":")[0]
            n = gspread.utils.a1_to_rowcol(f"{letra}1")[1]
            resultado.append([[_texto(l[n - 1])] if len(l) >= n and l[n - 1] != "" else [] for l in self.dados])
        return resultado

    def update(self, faixa, valores, value_input_option="RAW"):
        self.gravacoes += 1
        self._escrever(faixa, valores, value_input_option)

    def batch_update(self, dados, value_input_option="RAW"):
        self.gravacoes += 1
        for item in dados:
            self._escrever(item["range"], item["values"], value_input_option)

    def append_rows(self, linhas, value_input_option="RAW"):
        self.gravacoes += 1
        for l in linhas:
            self.dados.append([self._como_planilha(v, value_input_option) for v in l])

    def format(self, faixa, formato):
        pass

    def clear(self):
        self.dados = []


class PlanilhaFalsa:
    def __init__(self):
        self.abas = {}

    def worksheet(self, nome):
        if nome not in self.abas:
            raise gspread.exceptions.WorksheetNotFound(nome)
        return self.abas[nome]

    def add_worksheet(self, title, rows, cols):
        self.abas[title] = AbaFalsa(title)
        return self.abas[title]

    def aba(self, nome):
        return self.abas[nome]


@pytest.fixture
def planilha(monkeypatch):
    """Planilha simulada com todas as abas vazias, e o app "zerado"."""
    falsa = PlanilhaFalsa()
    for nome in ["aquisicao", "arco_flecha", "machado", "swordplay", "rachar_lenha",
                 "vestimenta", "bardos", "feiticos", "beberrao"]:
        falsa.abas[nome] = AbaFalsa(nome)
    monkeypatch.setattr(aplicativo, "get_spreadsheet", lambda: falsa)
    aplicativo._abas_abertas.clear()
    aplicativo._cabecalhos_conferidos.clear()
    aplicativo._cache_resultados.clear()
    aplicativo._tentativas_codigo.clear()
    aplicativo.esquecer_cache_aquisicao()
    aplicativo._resumo_conferido = False
    monkeypatch.setattr(aplicativo.time, "sleep", lambda s: None)
    # Tarefas "em segundo plano" rodam na hora, para o teste ver o resultado.
    monkeypatch.setattr(aplicativo, "em_segundo_plano", lambda funcao, *args: funcao(*args))
    return falsa


@pytest.fixture
def drive(monkeypatch):
    """Drive simulado: guarda o que foi enviado (já comprimido pelo app)."""
    enviados = []

    def subir(file_storage, nome_base, folder_id=None):
        dados = aplicativo.compress_photo(file_storage.read())
        enviados.append({"nome": nome_base, "pasta": folder_id, "bytes": len(dados)})
        return f"https://drive.google.com/file/d/FOTO{len(enviados):06d}xyz/view"

    monkeypatch.setattr(aplicativo, "upload_photo_to_drive", subir)
    return enviados


def _cliente(codigo=False, **sessao):
    aplicativo.app.config["TESTING"] = True
    cliente = aplicativo.app.test_client()
    if codigo:
        cliente.set_cookie(aplicativo.COOKIE_CODIGO, aplicativo._marca_do_codigo("4321"))
    if sessao:
        with cliente.session_transaction() as s:
            s.update(sessao)
    return cliente


@pytest.fixture
def equipe():
    """Celular da equipe: já digitou o código e entrou com uma Conta Google qualquer."""
    return _cliente(codigo=True, user_email="atendente@exemplo.com", user_name="Atendente")


@pytest.fixture
def organizacao():
    return _cliente(user_email="org@exemplo.com", user_name="Organizador")


@pytest.fixture
def administracao():
    return _cliente(user_email="adm@exemplo.com", user_name="Administração")


@pytest.fixture
def anonimo():
    return _cliente()


def foto_jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (180, 40, 40)).save(buf, format="JPEG")
    return buf.getvalue()
