# app.py
import os
import io
import uuid
import json
import re
import hmac
import socket
import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from PIL import Image

# Sem isso, uma chamada de rede para o Google (Sheets/Drive/verificação de
# login) que travar por qualquer motivo fica esperando resposta para
# sempre. Com um tempo-limite global, a chamada falha sozinha, dentro do
# try/except de cada rota, e quem está usando o app vê uma mensagem de erro
# decente em vez de travar.
socket.setdefaulttimeout(25)

try:
    # pillow-heif só é instalado no Linux (Render): no Windows local ele exige
    # compilar uma biblioteca nativa e trava a instalação. Localmente, o app
    # funciona normal sem essa lib (só não comprime fotos .heic de iPhone).
    from pillow_heif import register_heif_opener
    register_heif_opener()  # permite ao Pillow abrir fotos .heic, se a lib estiver instalada
except ImportError:
    pass

from config import (
    ACTIVITIES,
    MODE_OPTIONS,
    PAYMENT_OPTIONS,
    SHEET_HEADERS,
    NOME_ABA_AQUISICAO,
    NOME_ABA_RESUMO,
    SITUACAO_TROCOU,
    SITUACAO_TROCA,
    FORMA_TROCA,
    TORNEIO_FISICOS,
    TORNEIO_CULTURAIS,
    TODOS_TORNEIOS,
    score_headers,
    sheet_headers_for,
)

# Lê as variáveis de um arquivo .env na mesma pasta, se ele existir.
# load_dotenv() não sobrescreve uma variável que já exista no ambiente.
load_dotenv()

app = Flask(__name__)

# Atrás de um proxy que termina HTTPS (Render, ngrok), o Flask "acha" que a
# conexão é HTTP simples — e o Google recusa o botão de login. O ProxyFix
# faz o Flask confiar nos cabeçalhos X-Forwarded-* desses serviços.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not app.secret_key:
    # Sem FLASK_SECRET_KEY, as sessões não sobrevivem a um reinício (e, com
    # 2 processos no gunicorn, cada um teria a sua chave). Serve só para
    # testar localmente — no Render, a variável precisa estar definida.
    app.secret_key = os.urandom(24)
    app.logger.warning("FLASK_SECRET_KEY não definida: usando chave temporária (só para teste local).")

MAX_UPLOAD_MB = 16
app.config.update(
    # v3: a sessão (login Google e código da equipe) dura 7 dias no aparelho,
    # o suficiente para o evento inteiro sem precisar entrar de novo.
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_SAMESITE="Lax",
    # No Render (que define RENDER=true) o cookie só trafega por HTTPS.
    # Localmente (http://localhost) isso ficaria desligado.
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
    # v3: limite de tamanho de qualquer envio. Antes não havia limite, e um
    # arquivo enorme podia estourar a memória do plano gratuito (512MB).
    MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
)

ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}

# ---------------------------------------------------------------------------
# Fuso horário do evento (v3)
# ---------------------------------------------------------------------------
# O Render roda em UTC: sem isso, data_hora saía 3 horas adiantada. O Brasil
# não tem horário de verão desde 2019; se o fuso nomeado não estiver
# disponível (Windows sem a base de fusos), usa UTC-3 fixo.
try:
    from zoneinfo import ZoneInfo
    FUSO_EVENTO = ZoneInfo("America/Sao_Paulo")
except Exception:  # noqa: BLE001
    FUSO_EVENTO = timezone(timedelta(hours=-3))


def agora_texto():
    return datetime.now(FUSO_EVENTO).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Acessos (v3)
# ---------------------------------------------------------------------------
#   CODIGO_EQUIPE        -> código do evento, combinado com a equipe. Pedido
#                           uma vez por celular em Competições e Aquisição.
#                           Troque a cada evento no painel do Render. Se
#                           ficar vazio, nada é pedido (útil para teste local).
#   EMAIL_ORGANIZACAO    -> e-mail(s) Google do organizador: além do que a
#                           equipe faz, registra desempates e corrige notas.
#   EMAIL_ADMINISTRACAO  -> e-mail(s) Google da administração: tudo o que a
#                           organização faz, mais a área de Administração
#                           (trocas, preparar para arquivo, resumo).
#   Mais de um e-mail: separe por vírgula. Organização e administração
#   entram com o login Google e não precisam do código.
#
#   GOOGLE_OAUTH_CLIENT_ID -> Client ID OAuth "Aplicativo da Web" do login.
#   ALLOWED_EMAILS         -> opcional; se preenchida, só esses e-mails
#                             conseguem entrar com o Google.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")


def _lista_de_emails(variavel):
    return {e.strip().lower() for e in os.environ.get(variavel, "").split(",") if e.strip()}


ALLOWED_EMAILS = _lista_de_emails("ALLOWED_EMAILS")
EMAILS_ORGANIZACAO = _lista_de_emails("EMAIL_ORGANIZACAO")
EMAILS_ADMINISTRACAO = _lista_de_emails("EMAIL_ADMINISTRACAO")
CODIGO_EQUIPE = os.environ.get("CODIGO_EQUIPE", "").strip()

NIVEIS_DE_ACESSO = {"equipe": 1, "organizacao": 2, "administracao": 3}
MENSAGENS_SEM_ACESSO = {
    "equipe": "Falta o código da equipe neste celular. Atualize a página para digitar o código.",
    "organizacao": "Só a organização pode fazer isso (entre com o e-mail Google da organização).",
    "administracao": "Só a administração pode fazer isso.",
}


COOKIE_CODIGO = "codigo_equipe"
DURACAO_CODIGO = timedelta(days=7)


def _marca_do_codigo(codigo):
    """O que fica guardado no celular não é o código em si, e sim uma marca
    dele (assinada com a FLASK_SECRET_KEY): se o código mudar no Render,
    todo mundo precisa digitar o novo.

    Fica num cookie próprio, separado da sessão: quando o Google devolve a
    pessoa ao app depois do login, o navegador não envia os cookies (é um
    envio vindo de outro site), e a sessão nova substituiria a antiga — se o
    código estivesse na sessão, ele se perderia a cada login."""
    chave = app.secret_key if isinstance(app.secret_key, bytes) else app.secret_key.encode()
    return hmac.new(chave, f"codigo:{codigo}".encode(), hashlib.sha256).hexdigest()[:32]


def papel_atual():
    """Quem está usando: "administracao", "organizacao", "equipe" ou None."""
    email = (session.get("user_email") or "").lower()
    if email and email in EMAILS_ADMINISTRACAO:
        return "administracao"
    if email and email in EMAILS_ORGANIZACAO:
        return "organizacao"
    marca = request.cookies.get(COOKIE_CODIGO, "")
    if not CODIGO_EQUIPE or hmac.compare_digest(marca, _marca_do_codigo(CODIGO_EQUIPE)):
        return "equipe"
    return None


def tem_acesso(minimo):
    papel = papel_atual()
    return papel is not None and NIVEIS_DE_ACESSO[papel] >= NIVEIS_DE_ACESSO[minimo]


def exige(minimo):
    """Protege uma rota: "equipe" (código ou e-mail da organização/administração),
    "organizacao" ou "administracao" (só pelo e-mail Google)."""
    def decorador(view_func):
        @wraps(view_func)
        def protegida(*args, **kwargs):
            if tem_acesso(minimo):
                return view_func(*args, **kwargs)
            if request.method != "GET":
                return jsonify({"ok": False, "errors": [MENSAGENS_SEM_ACESSO[minimo]]}), 403
            if minimo == "equipe":
                return redirect(url_for("entrar_equipe", next=request.path))
            if "user_email" not in session:
                return redirect(url_for("login", next=request.path))
            return render_template("erro.html", codigo=403), 403
        return protegida
    return decorador


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_email" not in session:
            if request.method == "GET":
                return redirect(url_for("login", next=request.path))
            return jsonify({"ok": False, "errors": ["Sessão expirada. Faça login novamente."]}), 401
        return view_func(*args, **kwargs)
    return wrapped


@app.context_processor
def contexto_de_acesso():
    papel = papel_atual()
    return {
        "papel": papel,
        "eh_organizacao": papel in ("organizacao", "administracao"),
        "eh_administracao": papel == "administracao",
    }


# Limite de tentativas erradas do código, por endereço de internet (v3):
# 5 erros em 10 minutos bloqueiam novas tentativas por 10 minutos.
LIMITE_TENTATIVAS_CODIGO = 5
JANELA_TENTATIVAS_S = 600
_tentativas_codigo = {}
_trava_tentativas = threading.Lock()


def _codigo_bloqueado(ip):
    with _trava_tentativas:
        agora_ts = time.time()
        recentes = [t for t in _tentativas_codigo.get(ip, []) if agora_ts - t < JANELA_TENTATIVAS_S]
        _tentativas_codigo[ip] = recentes
        return len(recentes) >= LIMITE_TENTATIVAS_CODIGO


def _registrar_codigo_errado(ip):
    with _trava_tentativas:
        _tentativas_codigo.setdefault(ip, []).append(time.time())


# ---------------------------------------------------------------------------
# Configuração Google (Sheets + Drive)
# ---------------------------------------------------------------------------
# Todas as credenciais vêm de variáveis de ambiente — nunca ficam no código.
#   GOOGLE_SERVICE_ACCOUNT_FILE  -> caminho para o .json da service account
#   GOOGLE_SHEET_ID              -> ID da planilha (está na URL do Sheets)
#   GOOGLE_DRIVE_FOLDER_ID       -> pasta PRIVADA dos comprovantes de PIX
#   GOOGLE_DRIVE_ALVOS_FOLDER_ID -> pasta (também privada) das fotos dos alvos;
#                                   Resultados mostra as fotos pelo próprio app

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
DRIVE_ALVOS_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ALVOS_FOLDER_ID")

# Upload de fotos: NÃO usa a service account (contas de serviço não têm cota
# de armazenamento própria no Drive). Usa uma autorização OAuth feita uma
# única vez com a conta pessoal (rode setup_drive_auth.py).
GOOGLE_DRIVE_TOKEN_FILE = os.environ.get("GOOGLE_DRIVE_TOKEN_FILE", "drive_token.json")
DRIVE_UPLOAD_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_gspread_client = None
_drive_local = threading.local()
_em_paralelo = ThreadPoolExecutor(max_workers=8)


def em_segundo_plano(funcao, *args):
    """Roda uma tarefa depois da resposta, sem fazer ninguém esperar."""
    threading.Thread(target=funcao, args=args, daemon=True).start()


def get_gspread_client():
    """Cria (uma vez) e reaproveita o cliente do gspread (via service account)."""
    global _gspread_client
    if _gspread_client is None:
        import gspread
        from google.oauth2.service_account import Credentials

        if not SERVICE_ACCOUNT_FILE:
            raise RuntimeError(
                "A variável GOOGLE_SERVICE_ACCOUNT_FILE não está definida. "
                "Informe o caminho do .json da service account e reinicie o app."
            )
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            raise RuntimeError(
                f"Não encontrei o arquivo de credenciais em '{SERVICE_ACCOUNT_FILE}'. "
                "Confira se o caminho em GOOGLE_SERVICE_ACCOUNT_FILE está correto."
            )

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        try:
            creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        except Exception as exc:
            raise RuntimeError(
                f"O arquivo '{SERVICE_ACCOUNT_FILE}' não é um JSON de service account válido "
                f"(pode estar vazio ou corrompido). Baixe a chave de novo no Google Cloud "
                f"Console se precisar. Erro original: {exc}"
            ) from exc

        _gspread_client = gspread.authorize(creds)
    return _gspread_client


def get_drive_service():
    """Cliente do Google Drive, autenticado com a SUA conta pessoal (não a
    service account). Com o gunicorn usando threads, dois envios podem usar
    o Drive ao mesmo tempo — e o cliente do Drive (httplib2) não pode ser
    compartilhado entre threads. Então cada thread ganha o seu."""
    service = getattr(_drive_local, "service", None)
    if service is None:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request as GoogleAuthRequest

        if not os.path.exists(GOOGLE_DRIVE_TOKEN_FILE):
            raise RuntimeError(
                f"Autorização do Drive não encontrada ({GOOGLE_DRIVE_TOKEN_FILE}). "
                "Rode 'python setup_drive_auth.py' uma vez, na sua máquina, para autorizar."
            )

        creds = Credentials.from_authorized_user_file(GOOGLE_DRIVE_TOKEN_FILE, DRIVE_UPLOAD_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            # No Render o arquivo é "só leitura" (Secret Files): a renovação
            # vale só na memória, o que basta — na próxima vez renova de novo.
            try:
                with open(GOOGLE_DRIVE_TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except OSError:
                pass

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        _drive_local.service = service
    return service


_spreadsheet = None


def get_spreadsheet():
    """Abre (uma vez) e reaproveita o objeto da planilha mestra inteira."""
    global _spreadsheet
    if _spreadsheet is None:
        client = get_gspread_client()

        if not SHEET_ID:
            raise RuntimeError("A variável GOOGLE_SHEET_ID não está definida.")

        try:
            _spreadsheet = client.open_by_key(SHEET_ID)
        except Exception as exc:
            raise RuntimeError(
                f"Não consegui abrir a planilha com ID '{SHEET_ID}': {exc}. "
                "Confira se o ID está certo (é o trecho da URL entre /d/ e /edit) e se a "
                "planilha foi compartilhada como Editor com o e-mail da service account "
                "(campo client_email no arquivo .json)."
            ) from exc
    return _spreadsheet


# Formato de moeda aplicado às colunas de valor (v3: os valores agora são
# gravados como números, e não como texto "R$ 10,00" — assim as somas
# funcionam em qualquer configuração de idioma da planilha).
FORMATO_MOEDA = {"numberFormat": {"type": "CURRENCY", "pattern": '"R$" #,##0.00'}}

_cabecalhos_conferidos = set()
# Cada Spreadsheet.worksheet(nome) do gspread faz uma chamada ao Google só
# para achar a aba. Guardamos a aba já encontrada e reaproveitamos.
# Se renomear/recriar uma aba com o app no ar, reinicie o serviço no Render.
_abas_abertas = {}


def letra_da_coluna(numero):
    """1 -> A, 26 -> Z, 27 -> AA."""
    letras = ""
    while numero:
        numero, resto = divmod(numero - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def get_worksheet(sheet_name=None, headers=None):
    """Abre uma aba da planilha mestra pelo nome (padrão: a aba da Aquisição)
    e garante que o cabeçalho dela existe.

    Atenção: o app lê e grava as colunas pela POSIÇÃO. Se o cabeçalho da
    linha 1 estiver diferente do esperado, ele é reescrito. Por isso, nunca
    insira colunas no meio das abas — colunas extras, só depois da última."""
    sh = get_spreadsheet()
    sheet_name = sheet_name or NOME_ABA_AQUISICAO
    headers = headers or SHEET_HEADERS

    try:
        ws = _abas_abertas.get(sheet_name) or tentar_google(sh.worksheet, sheet_name)
        _abas_abertas[sheet_name] = ws
    except Exception as exc:
        raise RuntimeError(
            f"Não encontrei a aba '{sheet_name}' na planilha. Confira se o nome "
            f"está exatamente igual (maiúsculas e acentos importam). "
            f"Erro original: {exc}"
        ) from exc

    # O cabeçalho é conferido só na primeira vez que cada aba é aberta por
    # este processo (economiza uma leitura no Google a cada envio).
    chave = (sheet_name, tuple(headers))
    if chave not in _cabecalhos_conferidos:
        first_row = tentar_google(ws.row_values, 1)
        if first_row[:len(headers)] != headers:
            tentar_google(ws.update, "A1", [headers])
        if sheet_name == NOME_ABA_AQUISICAO:
            try:
                inicio = letra_da_coluna(headers.index("valor_unitario") + 1)
                fim = letra_da_coluna(headers.index("valor_total") + 1)
                tentar_google(ws.format, f"{inicio}:{fim}", FORMATO_MOEDA)
            except Exception as exc:  # noqa: BLE001 — só aparência; não trava nada
                app.logger.warning("Não consegui formatar as colunas de valor como moeda: %r", exc)
        _cabecalhos_conferidos.add(chave)
    return ws


def read_modality_rows(sheet_name, headers):
    """Lê todas as linhas de dados de uma aba de atividade, como lista de
    dicionários. Cada item inclui "_row" (número real da linha na planilha,
    contando o cabeçalho)."""
    ws = get_worksheet(sheet_name, headers)
    all_values = tentar_google(ws.get_all_values)
    result = []
    for row_number, row in enumerate(all_values[1:], start=2):
        padded = row + [""] * (len(headers) - len(row))
        item = dict(zip(headers, padded))
        item["_row"] = row_number
        result.append(item)
    return result


def _normalizar(texto):
    return " ".join(str(texto or "").split()).lower()


def _inteiro(valor):
    """"3" -> 3, "3.0" -> 3, "" ou texto -> None."""
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if numero != numero or not numero.is_integer():  # NaN ou com casas decimais
        return None
    return int(numero)


def _numero(valor):
    try:
        numero = float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return None if numero != numero else numero


def linhas_validas(rows):
    """Linhas que contam nas listas e nos resultados (v3): sem as linhas em
    branco, sem quem trocou de atividade e sem repetição do mesmo inscrito
    (se duas gravações simultâneas incluírem a mesma pessoa, vale a primeira)."""
    vistos = set()
    validas = []
    for r in rows:
        if not (r.get("nome") or "").strip():
            continue
        if _normalizar(r.get("situacao")) == SITUACAO_TROCOU:
            continue
        id_inscricao = (r.get("id_inscricao") or "").strip()
        if id_inscricao:
            if id_inscricao in vistos:
                continue
            vistos.add(id_inscricao)
        validas.append(r)
    return validas


def localizar_linha(rows, row_number, id_inscricao, nome):
    """Acha a pessoa certa na aba, mesmo que a planilha tenha sido reordenada
    ou tenha linhas apagadas depois que a tela foi aberta (v3).

    Com código de inscrição, procura por ele (a linha pode ter mudado de
    lugar). Sem código (linha incluída à mão na planilha), aceita a linha
    informada pela tela só se o nome ainda for o mesmo. None = não achou."""
    id_inscricao = (id_inscricao or "").strip()
    if id_inscricao:
        for r in rows:
            if (r.get("id_inscricao") or "").strip() == id_inscricao:
                return r
        return None
    for r in rows:
        if r["_row"] == row_number:
            return r if _normalizar(r.get("nome")) == _normalizar(nome) else None
    return None


MENSAGEM_LISTA_MUDOU = (
    "A lista mudou desde que esta tela foi aberta (alguém mexeu na planilha). "
    "Atualize a página e confira a pessoa antes de enviar de novo — nada foi salvo."
)


def ordenar_por_nome(rows):
    return sorted(rows, key=lambda r: r.get("nome", "").strip().lower())


def marcar_homonimos(rows):
    """Marca (com '_duplicado') as linhas cujo nome se repete na lista —
    a tela usa isso para mostrar o telefone junto e diferenciar as pessoas."""
    contagem = {}
    for r in rows:
        chave = _normalizar(r.get("nome"))
        contagem[chave] = contagem.get(chave, 0) + 1
    for r in rows:
        r["_duplicado"] = contagem.get(_normalizar(r.get("nome")), 0) > 1
    return rows


# ---------------------------------------------------------------------------
# Tratamento de erros com o Google
# ---------------------------------------------------------------------------
# Falhas passageiras do Google (limite de uso por minuto, instabilidade,
# conexão lenta) são tentadas de novo automaticamente, e quem está usando o
# app recebe mensagens claras em vez de textos técnicos — os detalhes vão
# para o log do Render.
_STATUS_PASSAGEIROS = {429, 500, 502, 503, 504}
_STATUS_SEGUROS_PARA_REPETIR_GRAVACAO = {429, 503}  # o Google recusou: nada foi gravado


def _status_http(exc):
    """Código HTTP de um erro do Google (gspread ou Drive), ou None.

    v3 — correção: antes era "exc.response or exc.resp". Só que, no requests,
    uma resposta de ERRO vale False num teste de verdade (bool(resposta) é
    False para 4xx/5xx). Resultado: os erros da planilha chegavam sempre
    "sem código", e as novas tentativas automáticas nunca aconteciam para eles."""
    for atributo in ("response", "resp"):
        resposta = getattr(exc, atributo, None)
        if resposta is None:
            continue
        status = getattr(resposta, "status_code", None)
        if status is None:
            status = getattr(resposta, "status", None)
        try:
            return int(status)
        except (TypeError, ValueError):
            continue
    return None


def _falha_de_conexao(exc):
    import requests
    return isinstance(exc, (TimeoutError, socket.timeout, ConnectionError, requests.exceptions.RequestException))


def tentar_google(fn, *args, repetivel=True, **kwargs):
    """Chama o Google e, se a falha for passageira, tenta de novo (até 3
    vezes no total). Espera 1s e 2s entre as tentativas; quando o Google diz
    que o limite por minuto estourou (429), espera um pouco mais (2s e 4s).

    repetivel=False é para gravações que acrescentam linhas (append): nesse
    caso só repete quando o Google recusou explicitamente (limite de uso ou
    indisponível), porque numa conexão cortada a linha pode já ter sido
    gravada, e repetir criaria linha duplicada."""
    tentativa = 0
    while True:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            status = _status_http(exc)
            if repetivel:
                passageira = status in _STATUS_PASSAGEIROS or _falha_de_conexao(exc)
            else:
                passageira = status in _STATUS_SEGUROS_PARA_REPETIR_GRAVACAO
            if not passageira or tentativa >= 2:
                raise
            espera = (2, 4)[tentativa] if status == 429 else (1, 2)[tentativa]
            tentativa += 1
            app.logger.warning("Falha passageira do Google (%s); tentando de novo em %ss", exc, espera)
            time.sleep(espera)


def mensagem_amigavel(exc, acao):
    """Transforma um erro técnico em uma mensagem que a equipe entende.
    `acao` completa a frase: "Não foi possível <acao> agora"."""
    app.logger.error("Falha ao %s: %r", acao, exc, exc_info=exc)
    if isinstance(exc, RuntimeError):
        # Erros de configuração escritos por nós (aba com nome errado,
        # credencial ausente): a mensagem já diz o que fazer.
        return str(exc)
    status = _status_http(exc)
    if status == 429:
        return ("O Google está recebendo muitos envios ao mesmo tempo. Aguarde uns "
                "10 segundos e tente de novo.")
    if _falha_de_conexao(exc) or status in _STATUS_PASSAGEIROS:
        return (f"Não foi possível {acao} agora: a conexão com o Google falhou ou demorou "
                "demais. Tente de novo em alguns segundos.")
    return (f"Não foi possível {acao} agora. Tente de novo em alguns segundos; se continuar, "
            "avise a organização.")


def sanitize_cell(value):
    """Evita "injeção de fórmula" em planilhas: se um texto vindo de quem
    preenche o formulário começar com um caractere que o Google Sheets
    interpreta como início de fórmula (=, +, -, @), prefixa com aspas
    simples para forçar leitura como texto puro."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def como_texto(valor):
    """Grava um código sempre como texto (apóstrofo na frente): sem isso, o
    Sheets "traduz" códigos como 12e45678 (notação científica) ou 00123456
    (perde os zeros)."""
    return "'" + valor if valor else ""


# ---------------------------------------------------------------------------
# Fotos
# ---------------------------------------------------------------------------
# Fotos são redimensionadas e recomprimidas antes de subir para o Drive —
# o comprovante só precisa ser legível, não em alta resolução.
MAX_PHOTO_DIMENSION = 1600   # pixels no lado maior
TARGET_PHOTO_BYTES = 700_000  # ~0,7MB de alvo (bem abaixo de 1MB)
MIN_JPEG_QUALITY = 35         # não comprime além disso, para manter legível


class FotoInvalida(Exception):
    """O arquivo enviado como foto não é uma imagem que dê para abrir."""


def compress_photo(file_bytes):
    """Confere que é uma imagem de verdade e devolve um JPEG de ~0,7MB.

    v3: antes, um arquivo que não fosse imagem passava direto e ia para o
    Drive com o tipo que o celular dissesse (até uma página HTML). Agora,
    se o Pillow não conseguir abrir, levanta FotoInvalida.

    O próprio celular já comprime a foto antes de enviar. Se chegar um JPEG
    que já está dentro do tamanho-alvo, não recomprime (poupa o processador
    fraco do plano gratuito do Render)."""
    if file_bytes[:3] == b"\xff\xd8\xff" and len(file_bytes) <= TARGET_PHOTO_BYTES:
        try:
            Image.open(io.BytesIO(file_bytes)).verify()
        except Exception as exc:  # noqa: BLE001
            raise FotoInvalida() from exc
        return file_bytes
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = img.convert("RGB")  # remove transparência/CMYK, garante JPEG válido
    except Exception as exc:  # noqa: BLE001
        raise FotoInvalida() from exc

    img.thumbnail((MAX_PHOTO_DIMENSION, MAX_PHOTO_DIMENSION), Image.LANCZOS)

    quality = 85
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= TARGET_PHOTO_BYTES or quality <= MIN_JPEG_QUALITY:
            return data
        quality -= 10


def upload_photo_to_drive(file_storage, nome_base, folder_id=None):
    """Sobe a foto para o Drive (sempre como JPEG) e devolve o link dela.
    As duas pastas (comprovantes e alvos) ficam privadas."""
    from googleapiclient.http import MediaIoBaseUpload

    dados = compress_photo(file_storage.read())
    service = get_drive_service()
    media = MediaIoBaseUpload(io.BytesIO(dados), mimetype="image/jpeg", resumable=False)

    file_metadata = {"name": f"{nome_base}.jpg"}
    if folder_id:
        file_metadata["parents"] = [folder_id]

    created = tentar_google(service.files().create(body=file_metadata, media_body=media, fields="id").execute)
    return f"https://drive.google.com/file/d/{created['id']}/view"


def format_brl(value):
    """Formata um número como moeda brasileira: 1234.5 -> 'R$ 1.234,50'. None vira ''."""
    if value is None:
        return ""
    texto = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {texto}" if value < 0 else f"R$ {texto}"


def _valor(numero):
    """Valor para a planilha: número com 2 casas (ou vazio se não há preço)."""
    return "" if numero is None else round(float(numero), 2)


def preco_de(activity_key, modo):
    raw = ACTIVITIES[activity_key].get("preco_unitario")
    return raw.get(modo) if isinstance(raw, dict) else raw


def montar_linha_aquisicao(**campos):
    """Linha da aba aquisicao na ordem de SHEET_HEADERS (o que não vier, fica vazio)."""
    return [campos.get(coluna, "") for coluna in SHEET_HEADERS]


# ---------------------------------------------------------------------------
# Inscrições nas abas das atividades (v3)
# ---------------------------------------------------------------------------
# Toda inclusão de inscritos passa por garantir_inscritos(), que só grava
# quem ainda não está na aba (pelo id_inscricao). Isso vale tanto para a
# cópia feita logo depois da compra quanto para a conferência automática
# feita quando o instrutor abre a lista.
_trava_inscricoes = threading.Lock()


def garantir_inscritos(activity_key, inscricoes):
    """Inclui na aba da atividade quem ainda não está lá. Devolve quantos incluiu."""
    if not inscricoes:
        return 0
    cfg = ACTIVITIES[activity_key]
    headers = sheet_headers_for(activity_key, cfg)
    col_id = headers.index("id_inscricao")

    with _trava_inscricoes:
        ws = get_worksheet(cfg["sheet_name"], headers)
        existentes = {str(v).strip() for v in tentar_google(ws.col_values, col_id + 1)[1:]}
        novas = []
        for i in inscricoes:
            if i["id_inscricao"] in existentes:
                continue
            existentes.add(i["id_inscricao"])
            linha = [""] * len(headers)
            linha[headers.index("nome")] = sanitize_cell(i["nome"])
            linha[headers.index("telefone")] = sanitize_cell(i["telefone"])
            if "cla" in headers:
                linha[headers.index("cla")] = sanitize_cell(i.get("cla", ""))
            linha[col_id] = como_texto(i["id_inscricao"])
            novas.append(linha)
        if novas:
            tentar_google(ws.append_rows, novas, value_input_option="USER_ENTERED", repetivel=False)
    return len(novas)


VALIDADE_CACHE_AQUISICAO_S = 15
_cache_aquisicao = {"quando": 0.0, "linhas": None}
_trava_cache_aquisicao = threading.Lock()


def linhas_da_aquisicao():
    """Linhas da aba aquisicao, guardadas em memória por 15 segundos (a
    conferência automática roda a cada abertura de lista; sem isso, cada uma
    gastaria uma leitura a mais da cota do Google)."""
    with _trava_cache_aquisicao:
        if _cache_aquisicao["linhas"] is not None and time.time() - _cache_aquisicao["quando"] < VALIDADE_CACHE_AQUISICAO_S:
            return _cache_aquisicao["linhas"]
    ws = get_worksheet()
    valores = tentar_google(ws.get_all_values)
    linhas = [dict(zip(SHEET_HEADERS, row + [""] * (len(SHEET_HEADERS) - len(row)))) for row in valores[1:]]
    with _trava_cache_aquisicao:
        _cache_aquisicao.update(quando=time.time(), linhas=linhas)
    return linhas


def esquecer_cache_aquisicao():
    with _trava_cache_aquisicao:
        _cache_aquisicao.update(quando=0.0, linhas=None)


def inscricoes_compradas(activity_key):
    """Quem comprou esta atividade em modo Competição, segundo a aba aquisicao."""
    label = ACTIVITIES[activity_key]["label"]
    inscricoes = []
    for linha in linhas_da_aquisicao():
        if linha["atividade"] != label or linha["modo"] != "Competição":
            continue
        quantidade = _inteiro(linha["quantidade"])
        if quantidade is None or quantidade <= 0:  # linhas de troca com -1 ficam de fora
            continue
        id_inscricao = (linha["id_inscricao"] or "").strip()
        nome = (linha["nome_competidor"] or "").strip()
        if not id_inscricao or not nome:
            continue
        inscricoes.append({
            "id_inscricao": id_inscricao,
            "nome": nome,
            "telefone": linha["telefone_competidor"],
            "cla": linha["cla_competidor"],
        })
    return inscricoes


def completar_inscricoes(activity_key, rows):
    """Conferência automática (v3): compara quem comprou (aba aquisicao) com
    a aba da atividade e inclui quem faltar — por exemplo, se a cópia feita
    logo depois da compra se perdeu num reinício do Render. Devolve True se
    incluiu alguém (aí a lista precisa ser lida de novo)."""
    ja_na_aba = {(r.get("id_inscricao") or "").strip() for r in rows}
    faltando = [i for i in inscricoes_compradas(activity_key) if i["id_inscricao"] not in ja_na_aba]
    if not faltando:
        return False
    incluidos = garantir_inscritos(activity_key, faltando)
    if incluidos:
        app.logger.warning("Conferência automática: %s inscrito(s) incluído(s) em %s", incluidos, activity_key)
    return incluidos > 0


_resumo_conferido = False


def tarefas_depois_da_compra(inscricoes_por_atividade):
    """Roda em segundo plano, depois que a compra já foi salva: copia os
    competidores para as abas das atividades e, uma vez por processo,
    confere a aba resumo. Se algo falhar aqui, a compra continua valendo e a
    conferência automática completa a lista do instrutor depois."""
    global _resumo_conferido
    for activity_key, inscricoes in inscricoes_por_atividade.items():
        try:
            garantir_inscritos(activity_key, inscricoes)
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Não consegui copiar os competidores para '%s': %r", activity_key, exc, exc_info=exc)
    if not _resumo_conferido:
        try:
            garantir_resumo()
            _resumo_conferido = True
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Não consegui atualizar a aba resumo: %r", exc, exc_info=exc)


# ---------------------------------------------------------------------------
# Aba "resumo" (v3) — fórmulas prontas, recriadas pelo próprio app
# ---------------------------------------------------------------------------

def montar_resumo(sep=";"):
    """Conteúdo da aba resumo. As funções vão com o nome em inglês (o Google
    aceita em qualquer idioma e mostra traduzido: SOMASES), mas o separador
    dos argumentos precisa ser o do idioma da planilha: ";" em português,
    "," em inglês. Na v3 inicial ia sempre ",", e numa planilha em português
    dava "erro de análise de fórmula"."""
    aba = f"{NOME_ABA_AQUISICAO}!"

    def col(nome):
        letra = letra_da_coluna(SHEET_HEADERS.index(nome) + 1)
        return f"{aba}${letra}:${letra}"

    atividade, modo, quantidade, total, forma = (
        col("atividade"), col("modo"), col("quantidade"), col("valor_total"), col("forma_pagamento"))

    linhas = [
        ["Resumo do evento — esta aba é refeita pelo app; não precisa editar nada aqui.", "", "", ""],
        ["Atividade", "Modo", "Quantidade", "Valor"],
    ]
    for cfg in ACTIVITIES.values():
        modos = MODE_OPTIONS if cfg["has_mode"] else [cfg["fixed_mode"]]
        for m in modos:
            criterio = f'{atividade}{sep}"{cfg["label"]}"{sep}{modo}{sep}"{m}"'
            linhas.append([cfg["label"], m, f"=SUMIFS({quantidade}{sep}{criterio})", f"=SUMIFS({total}{sep}{criterio})"])
    linhas.append(["", "", "", ""])
    linhas.append(["Forma de pagamento", "", "", "Valor"])
    for f in PAYMENT_OPTIONS:
        linhas.append([f, "", "", f'=SUMIF({forma}{sep}"{f}"{sep}{total})'])
    linhas.append(["Total geral", "", "", f"=SUM({total})"])
    linhas.append(["", "", "", ""])
    linhas.append([
        "Trocas: a atividade de saída recebe quantidade -1 e a de entrada +1. "
        "Só a diferença paga entra em PIX/Dinheiro; o resto aparece como \"Troca\" e se anula.",
        "", "", "",
    ])
    return linhas


def garantir_resumo():
    """Cria a aba resumo se ela não existir e (re)escreve as fórmulas."""
    import gspread
    sh = get_spreadsheet()
    try:
        ws = tentar_google(sh.worksheet, NOME_ABA_RESUMO)
    except gspread.exceptions.WorksheetNotFound:
        ws = tentar_google(sh.add_worksheet, title=NOME_ABA_RESUMO, rows=80, cols=6)
    # Idiomas que usam vírgula como separador de argumentos (ponto decimal);
    # os demais (português, espanhol, francês...) usam ponto e vírgula.
    idioma = (getattr(sh, "locale", "") or "").split("_")[0].lower()
    virgula = idioma in {"en", "ja", "zh", "ko", "th", "he", "iw", "hi", "ms", "fil", "tl"}
    for sep in ([",", ";"] if virgula else [";", ","]):
        valores = montar_resumo(sep)
        tentar_google(ws.clear)
        tentar_google(ws.update, "A1", valores, value_input_option="USER_ENTERED")
        # Confere se o Google entendeu a fórmula; se não, tenta o outro separador.
        conferencia = tentar_google(ws.acell, "C3").value or ""
        if not str(conferencia).startswith("#"):
            break
    tentar_google(ws.format, f"D3:D{len(valores)}", FORMATO_MOEDA)


# ---------------------------------------------------------------------------
# Validação da compra
# ---------------------------------------------------------------------------

def _digitos(texto):
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def telefone_valido(telefone):
    return 10 <= len(_digitos(telefone)) <= 11


def validate_submission(activities_payload, photo_file, forma_pagamento):
    """Retorna uma lista de mensagens de erro. Lista vazia = tudo certo."""
    errors = []

    tem_foto = bool(photo_file and photo_file.filename)

    if tem_foto:
        ext = photo_file.filename.rsplit(".", 1)[-1].lower() if "." in photo_file.filename else ""
        if ext not in ALLOWED_PHOTO_EXTENSIONS:
            errors.append("Formato de foto não suportado. Use JPG, PNG, WEBP ou HEIC.")

    if forma_pagamento not in PAYMENT_OPTIONS:
        errors.append("Informe a forma de pagamento (PIX ou Dinheiro).")

    if not activities_payload:
        errors.append("Marque ao menos uma atividade.")
        return errors  # sem atividades, não há mais o que validar

    for item in activities_payload:
        if not isinstance(item, dict):
            errors.append("Dados do formulário corrompidos. Atualize a página e tente de novo.")
            continue
        key = item.get("activity")
        cfg = ACTIVITIES.get(key)
        if cfg is None:
            errors.append(f"Atividade desconhecida: {key}.")
            continue

        label = cfg["label"]

        quantidade = item.get("quantidade")
        try:
            quantidade = int(quantidade)
            if quantidade <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"Informe uma quantidade válida para {label}.")

        if cfg["has_mode"]:
            modo = item.get("modo")
            if modo not in MODE_OPTIONS:
                errors.append(f"Informe se {label} é modo treino ou competição.")

        modo_efetivo = cfg.get("fixed_mode") or item.get("modo")
        requires_names = cfg.get("collects_competitor_names") and modo_efetivo == "Competição"
        if not requires_names:
            item["competidores"] = []  # treino não leva nomes
            continue

        raw_competidores = item.get("competidores") or []
        competidores = []
        for c in raw_competidores:
            if not isinstance(c, dict):
                continue
            nome = (c.get("nome") or "").strip()
            telefone = (c.get("telefone") or "").strip()
            cla = (c.get("cla") or "").strip() if cfg.get("collects_cla", True) else ""
            if not nome or not telefone:
                continue
            if not telefone_valido(telefone):
                errors.append(
                    f"Telefone de '{nome}' em {label} parece incompleto — "
                    f"inclua o DDD (ex.: 51999998888)."
                )
                continue
            competidores.append({"nome": nome, "telefone": telefone, "cla": cla})

        item["competidores"] = competidores  # normaliza para o resto do código usar
        if isinstance(quantidade, int) and quantidade > 0:
            if len(competidores) != quantidade:
                errors.append(
                    f"Informe nome e telefone (com DDD) de cada competidor de {label} "
                    f"({quantidade} esperado(s), {len(competidores)} completo(s))."
                )

    return errors


def calcular_total(activities_payload):
    """Total da compra pelos preços atuais do config.py (o mesmo que vai para a planilha)."""
    total = 0.0
    for item in activities_payload:
        cfg = ACTIVITIES[item["activity"]]
        preco = preco_de(item["activity"], cfg["fixed_mode"] or item.get("modo", ""))
        if preco is not None:
            total += preco * int(item["quantidade"])
    return round(total, 2)


def calcular_assinatura(activities_payload, forma_pagamento):
    """Resumo curto do CONTEÚDO da compra (v3). Serve para diferenciar uma
    nova tentativa da mesma compra (mesma assinatura: não grava de novo) de
    uma compra alterada que reaproveitou o mesmo código (assinatura
    diferente: avisa, em vez de dizer "já registrada" e perder a mudança)."""
    itens = []
    for item in activities_payload:
        cfg = ACTIVITIES[item["activity"]]
        competidores = sorted(
            [_normalizar(c["nome"]), _digitos(c["telefone"]), _normalizar(c.get("cla"))]
            for c in item.get("competidores") or []
        )
        itens.append([item["activity"], cfg["fixed_mode"] or item.get("modo", ""), int(item["quantidade"]), competidores])
    itens.sort()
    bruto = json.dumps([forma_pagamento, itens], ensure_ascii=False)
    return hashlib.sha256(bruto.encode()).hexdigest()[:12]


def compra_existente(purchase_id, ws=None):
    """Se esse código de compra já está na aba aquisicao, devolve a
    assinatura gravada com ele ("" se for de uma versão antiga, sem
    assinatura). Se não está, devolve None. Uma leitura só no Google."""
    ws = ws or get_worksheet()
    letra = letra_da_coluna(SHEET_HEADERS.index("assinatura") + 1)
    ids, assinaturas = tentar_google(ws.batch_get, ["A:A", f"{letra}:{letra}"])
    for i, linha in enumerate(ids):
        if i == 0 or not linha:
            continue
        if str(linha[0]).strip().lstrip("'") == purchase_id:
            return str(assinaturas[i][0]).strip() if i < len(assinaturas) and assinaturas[i] else ""
    return None


def resposta_compra_existente(purchase_id, assinatura_salva, assinatura_nova):
    if not assinatura_salva or assinatura_salva == assinatura_nova:
        return jsonify({"ok": True, "purchase_id": purchase_id, "avisos": [], "ja_registrada": True})
    return jsonify({
        "ok": False,
        "conteudo_diferente": True,
        "purchase_id": purchase_id,
        "errors": [
            f"A compra {purchase_id} já tinha sido registrada antes, com outros dados — "
            "por isso esta versão NÃO foi salva.",
            "Se esta é outra compra (outro cliente), toque em “Registrar como nova compra”, logo abaixo.",
            "Se o cliente mudou a compra anterior, não reenvie: chame a administração para registrar a troca.",
        ],
    }), 409


# ---------------------------------------------------------------------------
# Rotas: login, código da equipe, início
# ---------------------------------------------------------------------------

def safe_redirect_target(default_endpoint):
    """Evita redirecionamento aberto: só aceita caminhos internos (começando
    com '/', mas nunca '//', que poderia apontar para fora do site)."""
    next_url = request.args.get("next") or request.form.get("next")
    if next_url and next_url.startswith("/") and not next_url.startswith("//") and "\\" not in next_url:
        return next_url
    return url_for(default_endpoint)


@app.route("/login")
def login():
    if "user_email" in session:
        return redirect(safe_redirect_target("home"))
    return render_template(
        "login.html",
        google_client_id=GOOGLE_OAUTH_CLIENT_ID,
        error=request.args.get("error"),
        next=request.args.get("next", ""),
    )


@app.route("/auth/google", methods=["POST"])
def auth_google():
    # Proteção CSRF recomendada pelo Google para o fluxo de "login_uri":
    # o token vem tanto num cookie quanto no corpo do POST, e os dois devem bater.
    csrf_cookie = request.cookies.get("g_csrf_token")
    csrf_body = request.form.get("g_csrf_token")
    if not csrf_cookie or not csrf_body or csrf_cookie != csrf_body:
        return redirect(url_for("login", error="Falha de verificação de segurança. Tente novamente."))

    credential = request.form.get("credential")
    if not credential:
        return redirect(url_for("login", error="Não recebemos a credencial do Google. Tente novamente."))

    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_auth_requests

    try:
        idinfo = google_id_token.verify_oauth2_token(
            credential, google_auth_requests.Request(), GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError:
        return redirect(url_for("login", error="Não foi possível verificar o login com o Google."))

    # v3: só aceita e-mail confirmado pelo Google — é o e-mail que decide
    # quem é da organização e da administração.
    if not idinfo.get("email_verified"):
        return redirect(url_for("login", error="Esta Conta Google ainda não tem o e-mail confirmado."))

    email = (idinfo.get("email") or "").lower()
    name = idinfo.get("name", email)

    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS | EMAILS_ORGANIZACAO | EMAILS_ADMINISTRACAO:
        return redirect(url_for("login", error="Este e-mail não tem acesso liberado para o app."))

    session.permanent = True
    session["user_email"] = email
    session["user_name"] = name
    return redirect(safe_redirect_target("home"))


@app.route("/logout")
def logout():
    # Sai da Conta Google. O código da equipe (cookie próprio) continua
    # valendo neste celular.
    session.clear()
    return redirect(url_for("home"))


@app.route("/entrar-equipe", methods=["GET", "POST"])
def entrar_equipe():
    """Tela do código da equipe (v3). O código é digitado uma vez por
    celular e vale por 7 dias (ou até ser trocado no Render)."""
    destino = safe_redirect_target("home")
    if tem_acesso("equipe"):
        return redirect(destino)

    erro = None
    if request.method == "POST":
        ip = request.remote_addr or "desconhecido"
        if _codigo_bloqueado(ip):
            erro = "Muitas tentativas com o código errado. Espere 10 minutos e tente de novo."
        else:
            digitado = (request.form.get("codigo") or "").strip()
            if digitado and hmac.compare_digest(digitado, CODIGO_EQUIPE):
                resposta = redirect(destino)
                resposta.set_cookie(
                    COOKIE_CODIGO, _marca_do_codigo(CODIGO_EQUIPE),
                    max_age=int(DURACAO_CODIGO.total_seconds()), httponly=True,
                    samesite="Lax", secure=app.config["SESSION_COOKIE_SECURE"],
                )
                return resposta
            _registrar_codigo_errado(ip)
            erro = "Código incorreto. Confira com a organização."
    return render_template("entrar_equipe.html", erro=erro, next=request.values.get("next", ""))


@app.route("/")
def home():
    return render_template("home.html", user_name=session.get("user_name"))


@app.route("/service-worker.js")
def service_worker():
    """Servido na raiz (v3): um service worker só cuida das páginas que
    estão "abaixo" do endereço dele, e em /static/ não cuidava de nenhuma."""
    resposta = send_from_directory(app.static_folder, "service-worker.js", mimetype="application/javascript")
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


# ---------------------------------------------------------------------------
# Rotas: Competições
# ---------------------------------------------------------------------------

@app.route("/competicoes")
@exige("equipe")
def competicoes():
    fisicos = [(key, ACTIVITIES[key]) for key in TORNEIO_FISICOS]
    culturais = [(key, ACTIVITIES[key]) for key in TORNEIO_CULTURAIS]
    return render_template("competicoes_hub.html", fisicos=fisicos, culturais=culturais)


def _atividade_de_ranking(key):
    """Config da atividade se ela for do tipo "posição no ranking"
    (Swordplay, Rachar Lenha e as culturais), senão None."""
    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TODOS_TORNEIOS or cfg.get("num_tiros"):
        return None
    return cfg


def _atividade_de_pontuacao(key):
    """Config da atividade se ela for pontuada por tiros (Arco/Machado), senão None."""
    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TORNEIO_FISICOS or not cfg.get("num_tiros"):
        return None
    return cfg


def validar_notas(tiros, cfg):
    """Confere as notas: quantidade certa, inteiras, de 0 até a nota máxima.
    Devolve (lista de inteiros, None) ou (None, mensagem de erro)."""
    n = cfg["num_tiros"]
    maxima = cfg.get("nota_maxima")
    if not isinstance(tiros, list) or len(tiros) != n:
        return None, f"Informe as {n} notas."
    valores = []
    for v in tiros:
        try:
            numero = float(v)
        except (TypeError, ValueError):
            return None, "Cada nota precisa ser um número válido (0 ou mais)."
        if numero != numero or numero < 0:
            return None, "Cada nota precisa ser um número válido (0 ou mais)."
        if not numero.is_integer():
            return None, "Cada nota precisa ser um número inteiro (sem casas decimais)."
        if maxima is not None and numero > maxima:
            return None, f"Cada nota vai de 0 a {maxima}."
        valores.append(int(numero))
    return valores, None


def classificar_por_total(rows):
    """Classificação do Arco/Machado com empates (v3).

    Quem tem o mesmo total fica com a mesma colocação (ex.: 1º, 2º, 3º, 3º),
    marcado como empate. Se a organização registrou o desempate (coluna
    desempate: 1, 2, 3... dentro do grupo empatado), vale a ordem registrada.
    Cada linha ganha _posicao, _empate, _desempatado e _tamanho_grupo."""
    pontuados = [r for r in rows if _numero(r.get("total")) is not None]
    pontuados.sort(key=lambda r: -_numero(r["total"]))
    classificados = []
    posicao = 1
    i = 0
    while i < len(pontuados):
        total = _numero(pontuados[i]["total"])
        j = i
        while j < len(pontuados) and _numero(pontuados[j]["total"]) == total:
            j += 1
        grupo = pontuados[i:j]
        ordens = [_inteiro(r.get("desempate")) for r in grupo]
        resolvido = len(grupo) > 1 and None not in ordens and sorted(ordens) == list(range(1, len(grupo) + 1))
        if resolvido:
            grupo.sort(key=lambda r: _inteiro(r["desempate"]))
        else:
            grupo.sort(key=lambda r: _normalizar(r.get("nome")))
        for k, r in enumerate(grupo):
            r["_posicao"] = posicao + k if resolvido else posicao
            r["_empate"] = len(grupo) > 1 and not resolvido
            r["_desempatado"] = resolvido
            r["_tamanho_grupo"] = len(grupo)
        classificados.extend(grupo)
        posicao += len(grupo)
        i = j
    return classificados


def grupos_de_empate(classificados, ate_posicao=3):
    """Grupos de empatados (resolvidos ou não) que tocam o Top 3 — é onde o
    desempate importa para a premiação."""
    grupos = {}
    for r in classificados:
        if r["_tamanho_grupo"] > 1:
            grupos.setdefault(_numero(r["total"]), []).append(r)
    return [g for g in grupos.values() if min(r["_posicao"] for r in g) <= ate_posicao]


@app.route("/competicoes/<key>")
@exige("equipe")
def competicao_pontuar(key):
    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TODOS_TORNEIOS:
        return redirect(url_for("competicoes"))

    headers = sheet_headers_for(key, cfg)
    erro = None
    try:
        brutas = read_modality_rows(cfg["sheet_name"], headers)
        try:
            if completar_inscricoes(key, brutas):
                brutas = read_modality_rows(cfg["sheet_name"], headers)
        except Exception as exc:  # noqa: BLE001 — a conferência é um extra; a lista aparece mesmo assim
            app.logger.error("Conferência automática falhou em %s: %r", key, exc, exc_info=exc)
        rows = marcar_homonimos(ordenar_por_nome(linhas_validas(brutas)))
    except Exception as exc:  # noqa: BLE001
        rows = []
        erro = mensagem_amigavel(exc, "carregar a lista de inscritos")

    if cfg.get("num_tiros"):
        for r in rows:
            r["_tiros"] = [r.get(f"tiro{i}", "") for i in range(1, cfg["num_tiros"] + 1)]
        return render_template(
            "competicao_pontuar.html",
            cfg=cfg,
            key=key,
            rows=rows,
            tiro_indices=list(range(1, cfg["num_tiros"] + 1)),
            erro=erro,
        )

    # Sem num_tiros: atividade do tipo "posição no ranking" (Swordplay, Rachar
    # Lenha e as culturais) — mesma tela para todas.
    return render_template("competicao_ranking.html", cfg=cfg, key=key, rows=rows, erro=erro)


PRAZO_FOTO_NOTA_S = 35


@app.route("/competicoes/<key>/pontuar", methods=["POST"])
@exige("equipe")
def competicao_enviar_nota(key):
    from gspread.utils import rowcol_to_a1

    inicio = time.monotonic()
    cfg = _atividade_de_pontuacao(key)
    if not cfg:
        return jsonify({"ok": False, "errors": ["Atividade inválida."]}), 400

    try:
        row_number = int(request.form.get("row", ""))
        tiros = json.loads(request.form.get("tiros", "[]"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "errors": ["Dados inválidos — atualize a página e tente de novo."]}), 400
    id_inscricao = request.form.get("id_inscricao", "")
    nome = request.form.get("nome", "")
    foto = request.files.get("foto_alvo")

    if not foto or not foto.filename:
        return jsonify({"ok": False, "errors": ["Tire a foto do alvo antes de enviar."]}), 400
    valores, erro_notas = validar_notas(tiros, cfg)
    if erro_notas:
        return jsonify({"ok": False, "errors": [erro_notas]}), 400

    total = sum(valores)
    headers = score_headers(cfg["num_tiros"])
    col_foto = headers.index("foto_alvo") + 1

    # A foto começa a subir para o Drive ao mesmo tempo em que a planilha é conferida.
    envio_foto = _em_paralelo.submit(
        upload_photo_to_drive,
        foto,
        f"{cfg['sheet_name']}_{id_inscricao or 'linha' + str(row_number)}_{uuid.uuid4().hex[:6]}",
        folder_id=DRIVE_ALVOS_FOLDER_ID,
    )

    try:
        ws = get_worksheet(cfg["sheet_name"], headers)
        brutas = read_modality_rows(cfg["sheet_name"], headers)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "conferir a planilha")]}), 502

    alvo = localizar_linha(brutas, row_number, id_inscricao, nome)
    if alvo is None:
        return jsonify({"ok": False, "errors": [MENSAGEM_LISTA_MUDOU]}), 409
    if _normalizar(alvo.get("situacao")) == SITUACAO_TROCOU:
        return jsonify({"ok": False, "errors": ["Essa pessoa trocou de atividade. Atualize a página."]}), 409
    if alvo.get("total"):
        salvos = [_inteiro(alvo.get(f"tiro{i}")) for i in range(1, cfg["num_tiros"] + 1)]
        if salvos == valores:
            # A tentativa anterior chegou, só a resposta se perdeu: está tudo certo.
            return jsonify({"ok": True, "total": total, "ja_salva": True})
        return jsonify({
            "ok": False,
            "errors": [f"Essa pessoa já tem nota lançada (total {alvo.get('total')}). "
                       "Atualize a página para ver. Para corrigir, chame a organização."],
        }), 409

    # A foto é a prova do desempate: se não chegar ao Drive, a nota NÃO é salva.
    try:
        foto_link = envio_foto.result(timeout=max(1, PRAZO_FOTO_NOTA_S - (time.monotonic() - inicio)))
    except FotoInvalida:
        return jsonify({"ok": False, "errors": [
            "O arquivo escolhido não é uma foto. Toque em “Trocar foto do alvo”, tire a foto e envie de novo.",
        ]}), 400
    except Exception as exc:  # noqa: BLE001
        app.logger.error("Foto do alvo não chegou ao Drive (%s, linha %s): %r", key, alvo["_row"], exc, exc_info=exc)
        return jsonify({
            "ok": False,
            "errors": [
                "A foto do alvo não chegou ao Drive, então a nota não foi salva. "
                "As notas e a foto continuam na tela: toque em Enviar de novo.",
            ],
        }), 502

    try:
        inicio_a1 = rowcol_to_a1(alvo["_row"], 4)  # coluna D: logo após nome/cla/telefone
        fim_a1 = rowcol_to_a1(alvo["_row"], col_foto)
        tentar_google(ws.update, f"{inicio_a1}:{fim_a1}", [valores + [total, foto_link]], value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "gravar a nota")]}), 502

    esquecer_resultado(key)
    return jsonify({"ok": True, "total": total})


@app.route("/competicoes/<key>/corrigir", methods=["POST"])
@exige("organizacao")
def competicao_corrigir_nota(key):
    """Correção de nota já lançada (v3) — só organização e administração.
    acao "corrigir": troca as notas e mantém a foto do alvo.
    acao "limpar": apaga notas, total e foto; a pessoa volta a aparecer como
    "não pontuada" para o instrutor lançar de novo (com foto nova)."""
    from gspread.utils import rowcol_to_a1

    cfg = _atividade_de_pontuacao(key)
    if not cfg:
        return jsonify({"ok": False, "errors": ["Atividade inválida."]}), 400
    payload = request.get_json(silent=True) or {}
    acao = payload.get("acao")
    if acao not in ("corrigir", "limpar"):
        return jsonify({"ok": False, "errors": ["Ação inválida."]}), 400

    n = cfg["num_tiros"]
    headers = score_headers(n)
    valores = None
    if acao == "corrigir":
        valores, erro_notas = validar_notas(payload.get("tiros"), cfg)
        if erro_notas:
            return jsonify({"ok": False, "errors": [erro_notas]}), 400

    try:
        ws = get_worksheet(cfg["sheet_name"], headers)
        brutas = read_modality_rows(cfg["sheet_name"], headers)
        alvo = localizar_linha(brutas, payload.get("row"), payload.get("id_inscricao"), payload.get("nome"))
        if alvo is None:
            return jsonify({"ok": False, "errors": [MENSAGEM_LISTA_MUDOU]}), 409
        if not alvo.get("total"):
            return jsonify({"ok": False, "errors": [
                "Essa pessoa ainda não tem nota — o lançamento é pela tela normal, com a foto do alvo."]}), 409

        linha = alvo["_row"]
        if acao == "corrigir":
            notas = [valores + [sum(valores)]]
            fim_notas = headers.index("total") + 1
        else:
            notas = [[""] * (n + 2)]  # tiros, total e foto
            fim_notas = headers.index("foto_alvo") + 1
        col_desempate = headers.index("desempate") + 1
        tentar_google(ws.batch_update, [
            {"range": f"{rowcol_to_a1(linha, 4)}:{rowcol_to_a1(linha, fim_notas)}", "values": notas},
            # A nota mudou: um desempate registrado antes deixa de valer.
            {"range": f"{rowcol_to_a1(linha, col_desempate)}:{rowcol_to_a1(linha, col_desempate + 2)}",
             "values": [["", session.get("user_email", ""), agora_texto()]]},
        ], value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "corrigir a nota")]}), 502

    esquecer_resultado(key)
    return jsonify({"ok": True})


@app.route("/competicoes/<key>/desempate", methods=["POST"])
@exige("organizacao")
def competicao_desempate(key):
    """Registra a ordem decidida no desempate (v3) — só organização e
    administração. Recebe todas as pessoas de UM grupo empatado, cada uma
    com a ordem (1, 2, 3...)."""
    from gspread.utils import rowcol_to_a1

    cfg = _atividade_de_pontuacao(key)
    if not cfg:
        return jsonify({"ok": False, "errors": ["Atividade inválida."]}), 400
    itens = (request.get_json(silent=True) or {}).get("itens")
    if not isinstance(itens, list) or len(itens) < 2 or not all(isinstance(i, dict) for i in itens):
        return jsonify({"ok": False, "errors": ["Dados inválidos."]}), 400

    ordens = [_inteiro(i.get("ordem")) for i in itens]
    if None in ordens or sorted(ordens) != list(range(1, len(itens) + 1)):
        return jsonify({"ok": False, "errors": [
            f"Use cada número de 1 a {len(itens)} uma vez só (1 = quem ficou na frente)."]}), 400

    headers = score_headers(cfg["num_tiros"])
    try:
        ws = get_worksheet(cfg["sheet_name"], headers)
        brutas = read_modality_rows(cfg["sheet_name"], headers)
        validas = linhas_validas(brutas)
        alvos = [localizar_linha(validas, i.get("row"), i.get("id_inscricao"), i.get("nome")) for i in itens]
        if None in alvos:
            return jsonify({"ok": False, "errors": [MENSAGEM_LISTA_MUDOU]}), 409
        totais = {_numero(a.get("total")) for a in alvos}
        total_do_grupo = totais.pop() if len(totais) == 1 else None
        grupo_atual = {r["_row"] for r in validas if total_do_grupo is not None and _numero(r.get("total")) == total_do_grupo}
        if total_do_grupo is None or grupo_atual != {a["_row"] for a in alvos}:
            return jsonify({"ok": False, "errors": [
                "As notas desse empate mudaram desde que a tela foi aberta. Atualize a página."]}), 409

        col = headers.index("desempate") + 1
        tentar_google(ws.batch_update, [
            {"range": rowcol_to_a1(a["_row"], col), "values": [[ordem]]} for a, ordem in zip(alvos, ordens)
        ], value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "gravar o desempate")]}), 502

    esquecer_resultado(key)
    return jsonify({"ok": True})


@app.route("/competicoes/<key>/posicao", methods=["POST"])
@exige("equipe")
def competicao_enviar_posicao(key):
    """Grava as posições (v3).

    - A tela manda só o que mudou (não desfaz o que outro instrutor salvou).
    - Posição vazia apaga a posição daquela pessoa.
    - A conferência de posição repetida olha o RESULTADO FINAL do envio, e
      não cada pessoa contra o que já estava salvo — assim dá para trocar o
      1º com o 2º, ou reordenar vários de uma vez.
    - Ou grava tudo, ou não grava nada (uma única chamada ao Google)."""
    from gspread.utils import rowcol_to_a1

    cfg = _atividade_de_ranking(key)
    if not cfg:
        return jsonify({"ok": False, "errors": ["Atividade inválida."]}), 400

    payload = request.get_json(silent=True) or {}
    posicoes = payload.get("posicoes")
    if not isinstance(posicoes, list) or not all(isinstance(p, dict) for p in posicoes):
        return jsonify({"ok": False, "errors": ["Dados inválidos."]}), 400
    if not posicoes:
        return jsonify({"ok": True, "atualizados": 0})

    headers = sheet_headers_for(key, cfg)
    col_posicao = headers.index("posicao") + 1
    try:
        ws = get_worksheet(cfg["sheet_name"], headers)
        validas = linhas_validas(read_modality_rows(cfg["sheet_name"], headers))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "conferir a planilha")]}), 502

    final = {r["_row"]: _inteiro(r.get("posicao")) for r in validas}
    nomes = {r["_row"]: r.get("nome", "") for r in validas}
    alteracoes = {}
    erros = []
    for item in posicoes:
        alvo = localizar_linha(validas, item.get("row"), item.get("id_inscricao"), item.get("nome"))
        if alvo is None:
            erros.append(MENSAGEM_LISTA_MUDOU)
            break
        bruto = str(item.get("posicao") if item.get("posicao") is not None else "").strip()
        if bruto == "":
            nova = None
        else:
            nova = _inteiro(bruto)
            if nova is None or nova < 1:
                erros.append(f"Posição inválida para {alvo.get('nome')}: use números inteiros a partir de 1.")
                continue
        final[alvo["_row"]] = nova
        alteracoes[alvo["_row"]] = nova
    if erros:
        return jsonify({"ok": False, "errors": erros + ["Nada foi salvo."]}), 409 if MENSAGEM_LISTA_MUDOU in erros else 400

    donos = {}
    for linha, pos in final.items():
        if pos is not None:
            donos.setdefault(pos, []).append(linha)
    repetidas = [
        f"A posição {pos} ficaria com {' e '.join(nomes[l] for l in linhas)}."
        for pos, linhas in sorted(donos.items())
        if len(linhas) > 1 and any(l in alteracoes for l in linhas)
    ]
    if repetidas:
        return jsonify({"ok": False, "errors": repetidas + ["Ajuste e envie de novo — nada foi salvo."]}), 400

    mudancas = [
        {"range": rowcol_to_a1(linha, col_posicao), "values": [["" if pos is None else pos]]}
        for linha, pos in alteracoes.items()
    ]
    try:
        tentar_google(ws.batch_update, mudancas, value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "gravar as posições")]}), 502

    esquecer_resultado(key)
    return jsonify({"ok": True, "atualizados": len(mudancas)})


# ---------------------------------------------------------------------------
# Rotas: Resultados
# ---------------------------------------------------------------------------
# v3: o Top 3 de cada atividade fica guardado em memória por 30 segundos.
# Resultados é aberto sem login e é muito atualizado na hora da premiação;
# sem isso, cada atualização gastava uma leitura da cota do Google (60 por
# minuto para o app inteiro) e podia fazer compras e notas falharem.
VALIDADE_CACHE_RESULTADOS_S = 30
_cache_resultados = {}
_trava_cache_resultados = threading.Lock()


def esquecer_resultado(key):
    with _trava_cache_resultados:
        _cache_resultados.pop(key, None)


def podio_por_posicao(rows):
    """Top 3 das atividades por posição: sempre as posições 1, 2 e 3, com
    "a definir" no que ainda não foi lançado (v3)."""
    por_posicao = {}
    for r in rows:
        p = _inteiro(r.get("posicao"))
        if p in (1, 2, 3) and p not in por_posicao:
            por_posicao[p] = r
    if not por_posicao:
        return []
    return [dict(por_posicao[p], _posicao=p) if p in por_posicao else {"_posicao": p, "_a_definir": True}
            for p in (1, 2, 3)]


@app.route("/resultados")
def resultados():
    fisicos = [(key, ACTIVITIES[key]) for key in TORNEIO_FISICOS]
    culturais = [(key, ACTIVITIES[key]) for key in TORNEIO_CULTURAIS]
    return render_template("resultados_hub.html", fisicos=fisicos, culturais=culturais)


@app.route("/resultados/<key>")
def resultado_atividade(key):
    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TODOS_TORNEIOS:
        return redirect(url_for("resultados"))

    with _trava_cache_resultados:
        guardado = _cache_resultados.get(key)
    if guardado and time.time() - guardado[0] < VALIDADE_CACHE_RESULTADOS_S:
        podio, empates = guardado[1], guardado[2]
    else:
        try:
            rows = linhas_validas(read_modality_rows(cfg["sheet_name"], sheet_headers_for(key, cfg)))
        except Exception as exc:  # noqa: BLE001
            return render_template("resultado_torneio.html", cfg=cfg, key=key, podio=[], empates=[],
                                   erro=mensagem_amigavel(exc, "carregar os resultados"))
        empates = []
        if cfg.get("num_tiros"):
            classificados = classificar_por_total(rows)
            for r in classificados:
                r["_foto_id"] = id_da_foto(r.get("foto_alvo"))
            podio = [r for r in classificados if r["_posicao"] <= 3]
            # Empates que valem pódio (resolvidos ou não) — com todos os
            # integrantes, mesmo quem ficou em 4º depois do desempate, para
            # a organização poder refazer a ordem se precisar.
            empates = grupos_de_empate(classificados)
        else:
            podio = podio_por_posicao(rows)
        with _trava_cache_resultados:
            _cache_resultados[key] = (time.time(), podio, empates)

    # v3: o desempate é feito aqui, em Resultados, onde estão as fotos dos
    # alvos — e só aparece para a organização e a administração.
    if papel_atual() not in ("organizacao", "administracao"):
        empates = []
    return render_template("resultado_torneio.html", cfg=cfg, key=key, podio=podio, empates=empates, erro=None)


# --- Fotos dos alvos em Resultados ------------------------------------------
# O próprio app busca a foto no Drive (com a autorização que já tem) e
# entrega a imagem — quem está em Resultados não precisa de conta Google, e
# a pasta Alvos fica privada.
_ID_DRIVE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
_fotos_em_cache = {}  # id -> (bytes, mimetype); guarda poucas fotos (Top 3)
_LIMITE_CACHE_FOTOS = 30


def id_da_foto(link):
    """Extrai o ID do arquivo de um link do Drive (…/file/d/<ID>/view)."""
    m = re.search(r"/file/d/([A-Za-z0-9_-]+)", link or "")
    return m.group(1) if m else None


@app.route("/resultados/foto/<file_id>")
def foto_alvo(file_id):
    if not _ID_DRIVE.match(file_id) or not DRIVE_ALVOS_FOLDER_ID:
        return render_template("erro.html", codigo=404), 404

    if file_id not in _fotos_em_cache:
        try:
            service = get_drive_service()
            meta = tentar_google(service.files().get(fileId=file_id, fields="parents,mimeType").execute)
            # Só entrega fotos da pasta Alvos — nunca comprovantes de PIX —
            # e só se for mesmo uma imagem (v3).
            if DRIVE_ALVOS_FOLDER_ID not in (meta.get("parents") or []):
                return render_template("erro.html", codigo=404), 404
            if not (meta.get("mimeType") or "").startswith("image/"):
                return render_template("erro.html", codigo=404), 404
            conteudo = tentar_google(service.files().get_media(fileId=file_id).execute)
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Falha ao buscar a foto do alvo %s: %s", file_id, exc)
            return render_template("erro.html", codigo=500), 502
        if len(_fotos_em_cache) >= _LIMITE_CACHE_FOTOS:
            _fotos_em_cache.pop(next(iter(_fotos_em_cache)), None)
        _fotos_em_cache[file_id] = (conteudo, meta["mimeType"])

    conteudo, mimetype = _fotos_em_cache[file_id]
    resposta = app.response_class(conteudo, mimetype=mimetype)
    resposta.headers["Cache-Control"] = "public, max-age=86400"
    # O navegador fica proibido de "adivinhar" outro tipo de arquivo.
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resposta


# ---------------------------------------------------------------------------
# Rotas: Aquisição
# ---------------------------------------------------------------------------

@app.route("/aquisicao")
@login_required
@exige("equipe")
def aquisicao():
    prices = {key: cfg.get("preco_unitario") for key, cfg in ACTIVITIES.items()}
    return render_template(
        "index.html",
        activities=ACTIVITIES,
        mode_options=MODE_OPTIONS,
        payment_options=PAYMENT_OPTIONS,
        prices_json=json.dumps(prices),
        user_name=session.get("user_name"),
        user_email=session.get("user_email"),
    )


# Prazos do envio da compra, contados desde que ele chega ao servidor (v3).
# O celular desiste em 60s; o servidor nunca começa a gravar depois de 35s,
# para não gravar uma compra que o atendente já acha que falhou (e que ele
# reenviaria, gerando duplicata).
PRAZO_FOTO_COMPRA_S = 25
PRAZO_PARA_GRAVAR_S = 35


@app.route("/submit", methods=["POST"])
@login_required
@exige("equipe")
def submit():
    inicio = time.monotonic()
    try:
        activities_payload = json.loads(request.form.get("activities_json", "[]"))
    except json.JSONDecodeError:
        return jsonify({"ok": False, "errors": ["Dados do formulário corrompidos. Tente novamente."]}), 400
    if not isinstance(activities_payload, list):
        return jsonify({"ok": False, "errors": ["Dados do formulário corrompidos. Tente novamente."]}), 400

    photo_file = request.files.get("photo")
    forma_pagamento = request.form.get("forma_pagamento", "")
    responsavel_nome = session.get("user_name", "")
    responsavel_email = session.get("user_email", "")

    errors = validate_submission(activities_payload, photo_file, forma_pagamento)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    # v3: confere se o total que o atendente viu na tela é o mesmo que vai
    # para a planilha. Se um preço mudar no meio do evento, quem estava com
    # a tela aberta continuava vendo (e cobrando) o preço antigo.
    total_servidor = calcular_total(activities_payload)
    total_tela = _numero(request.form.get("total_exibido"))
    if total_tela is None or abs(total_tela - total_servidor) > 0.004:
        return jsonify({"ok": False, "precos_mudaram": True, "errors": [
            f"Os preços foram atualizados: o total certo desta compra é {format_brl(total_servidor)}"
            + (f" (a tela mostrava {format_brl(total_tela)})." if total_tela is not None else "."),
            "Atualize a página — o que foi preenchido não se perde —, confira o novo total com o cliente e envie de novo.",
        ]}), 409

    # O código da compra é criado pelo celular ANTES de enviar e reaproveitado
    # em qualquer nova tentativa: se a primeira chegou a ser gravada mas a
    # resposta não voltou (rede lenta), a segunda não vira compra duplicada.
    purchase_id = (request.form.get("purchase_id") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8}", purchase_id):
        purchase_id = uuid.uuid4().hex[:8]  # celular com app antigo: gera aqui
    assinatura = calcular_assinatura(activities_payload, forma_pagamento)

    # Com foto, ela começa a subir para o Drive ao mesmo tempo em que a
    # planilha confere se essa compra já existe.
    envio_foto = None
    if photo_file and photo_file.filename:
        envio_foto = _em_paralelo.submit(upload_photo_to_drive, photo_file, purchase_id, folder_id=DRIVE_FOLDER_ID)
        try:
            existente = compra_existente(purchase_id)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "conferir a planilha")]}), 502
        if existente is not None:
            return resposta_compra_existente(purchase_id, existente, assinatura)

    photo_link = ""
    if envio_foto is not None:
        try:
            photo_link = envio_foto.result(timeout=max(0.5, PRAZO_FOTO_COMPRA_S - (time.monotonic() - inicio)))
        except Exception as exc:  # noqa: BLE001 — foto é opcional: a compra é salva mesmo assim
            photo_link = "Imagem não recebida"
            app.logger.error("Comprovante não chegou ao Drive (compra %s salva mesmo assim): %r", purchase_id, exc)

    timestamp = agora_texto()
    rows = []
    inscricoes_por_atividade = {}
    numero_inscricao = 0
    for item in activities_payload:
        activity_key = item["activity"]
        cfg = ACTIVITIES[activity_key]
        modo = cfg["fixed_mode"] or item.get("modo", "")
        quantidade = int(item["quantidade"])
        preco = preco_de(activity_key, modo)
        comum = dict(
            id_compra=como_texto(purchase_id),
            data_hora=timestamp,
            atividade=cfg["label"],
            modo=modo,
            forma_pagamento=forma_pagamento,
            link_foto=photo_link,
            responsavel_nome=sanitize_cell(responsavel_nome),
            responsavel_email=responsavel_email,
            assinatura=assinatura,
        )

        competidores = item.get("competidores") or []
        if competidores:
            # Uma linha por competidor, cada uma com quantidade 1, e um código
            # de inscrição próprio que liga a compra à aba da atividade.
            for competidor in competidores:
                numero_inscricao += 1
                id_inscricao = f"{purchase_id}-{numero_inscricao}"
                rows.append(montar_linha_aquisicao(
                    **comum,
                    quantidade=1,
                    valor_unitario=_valor(preco),
                    valor_total=_valor(preco),
                    nome_competidor=sanitize_cell(competidor["nome"]),
                    telefone_competidor=sanitize_cell(competidor["telefone"]),
                    cla_competidor=sanitize_cell(competidor["cla"]),
                    id_inscricao=como_texto(id_inscricao),
                ))
                if cfg.get("sheet_name"):
                    inscricoes_por_atividade.setdefault(activity_key, []).append(dict(competidor, id_inscricao=id_inscricao))
        else:
            rows.append(montar_linha_aquisicao(
                **comum,
                quantidade=quantidade,
                valor_unitario=_valor(preco),
                valor_total=_valor(preco * quantidade if preco is not None else None),
            ))

    try:
        ws = get_worksheet()
        # Confere de novo logo antes de gravar: cobre o caso raro de duas
        # tentativas da mesma compra chegando quase juntas.
        existente = compra_existente(purchase_id, ws)
        if existente is not None:
            return resposta_compra_existente(purchase_id, existente, assinatura)
        if time.monotonic() - inicio > PRAZO_PARA_GRAVAR_S:
            app.logger.warning("Compra %s não gravada: envio passou de %ss", purchase_id, PRAZO_PARA_GRAVAR_S)
            return jsonify({"ok": False, "errors": [
                "A conexão estava lenta e o envio foi interrompido antes de gravar — nada foi salvo ainda.",
                "Toque em Enviar de novo.",
            ]}), 503
        tentar_google(ws.append_rows, rows, value_input_option="USER_ENTERED", repetivel=False)
    except Exception as exc:  # noqa: BLE001
        return jsonify({
            "ok": False,
            "errors": [
                mensagem_amigavel(exc, "registrar a compra na planilha"),
                "Pode tocar em Enviar de novo: se a compra tiver chegado, ela não será duplicada.",
            ],
        }), 502

    esquecer_cache_aquisicao()
    # A compra já está salva: a cópia para as abas das atividades roda em
    # segundo plano, e quem está atendendo recebe o "Compra registrada!" já.
    em_segundo_plano(tarefas_depois_da_compra, inscricoes_por_atividade)

    return jsonify({"ok": True, "purchase_id": purchase_id, "avisos": []})


# ---------------------------------------------------------------------------
# Rotas: Administração (v3) — só para os e-mails de EMAIL_ADMINISTRACAO
# ---------------------------------------------------------------------------

def _modo_valido(activity_key, modo):
    cfg = ACTIVITIES.get(activity_key)
    if not cfg:
        return None
    if cfg["has_mode"]:
        return modo if modo in MODE_OPTIONS else None
    return cfg["fixed_mode"]


def _e_competicao(activity_key, modo):
    return bool(ACTIVITIES[activity_key].get("collects_competitor_names")) and modo == "Competição"


def _tem_resultado(row):
    return bool((row.get("total") or "").strip() or (row.get("posicao") or "").strip())


@app.route("/administracao")
@exige("administracao")
def administracao():
    aviso_resumo = None
    try:
        garantir_resumo()
    except Exception as exc:  # noqa: BLE001
        aviso_resumo = mensagem_amigavel(exc, "atualizar a aba resumo")
    atividades = []
    for key, cfg in ACTIVITIES.items():
        modos = MODE_OPTIONS if cfg["has_mode"] else [cfg["fixed_mode"]]
        for modo in modos:
            atividades.append({
                "key": key,
                "modo": modo,
                "rotulo": f"{cfg['label']} — {modo}" if cfg["has_mode"] else cfg["label"],
                "preco": preco_de(key, modo),
                "competicao": _e_competicao(key, modo),
                "cla": bool(cfg.get("collects_cla", True)),
            })
    return render_template(
        "administracao.html",
        atividades=atividades,
        payment_options=PAYMENT_OPTIONS,
        aviso_resumo=aviso_resumo,
        user_name=session.get("user_name"),
    )


@app.route("/administracao/inscritos/<key>")
@exige("administracao")
def administracao_inscritos(key):
    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TODOS_TORNEIOS:
        return jsonify({"ok": False, "errors": ["Atividade inválida."]}), 400
    try:
        rows = ordenar_por_nome(linhas_validas(read_modality_rows(cfg["sheet_name"], sheet_headers_for(key, cfg))))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "carregar os inscritos")]}), 502
    return jsonify({"ok": True, "inscritos": [{
        "row": r["_row"],
        "id_inscricao": (r.get("id_inscricao") or "").strip(),
        "nome": r.get("nome", ""),
        "telefone": r.get("telefone", ""),
        "cla": r.get("cla", ""),
        "tem_resultado": _tem_resultado(r),
    } for r in rows]})


@app.route("/administracao/troca", methods=["POST"])
@exige("administracao")
def administracao_troca():
    """Troca de atividade (v3), em treino ou competição.

    Não mexe na compra original (no treino nem dá para saber qual foi).
    Registra a troca como uma operação própria, com um código novo:
      - saída:  atividade antiga, quantidade -1, valor -preço antigo ("Troca")
      - entrada: atividade nova, quantidade +1, valor +preço antigo ("Troca")
      - diferença (se a nova for mais cara): quantidade 0, valor da
        diferença, na forma de pagamento usada para completar.
    Assim o caixa só aumenta pelo que entrou de verdade, e a contagem e a
    receita de cada atividade ficam certas. Se a nova for mais barata, o
    valor pago passa inteiro para ela (não há devolução).

    Na competição, a pessoa sai da lista da atividade antiga (marcada como
    "trocou", não é apagada) e entra na lista da nova."""
    from gspread.utils import rowcol_to_a1

    # Vem como formulário (multipart), porque pode trazer a foto do
    # comprovante do PIX da diferença; os dados vão no campo "dados".
    try:
        payload = json.loads(request.form.get("dados") or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    foto = request.files.get("foto")
    sai = payload.get("sai") if isinstance(payload.get("sai"), dict) else {}
    entra = payload.get("entra") if isinstance(payload.get("entra"), dict) else {}

    id_troca = (payload.get("id_troca") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8}", id_troca):
        id_troca = uuid.uuid4().hex[:8]

    sai_key, entra_key = sai.get("atividade"), entra.get("atividade")
    sai_modo, entra_modo = _modo_valido(sai_key, sai.get("modo")), _modo_valido(entra_key, entra.get("modo"))
    if not sai_modo or not entra_modo:
        return jsonify({"ok": False, "errors": ["Escolha a atividade de saída e a de entrada."]}), 400
    if (sai_key, sai_modo) == (entra_key, entra_modo):
        return jsonify({"ok": False, "errors": ["A atividade de entrada é igual à de saída."]}), 400

    sai_cfg, entra_cfg = ACTIVITIES[sai_key], ACTIVITIES[entra_key]
    sai_comp, entra_comp = _e_competicao(sai_key, sai_modo), _e_competicao(entra_key, entra_modo)
    erros = []

    pessoa = {"nome": "", "telefone": "", "cla": ""}
    alvo_saida = None
    ws_saida = None
    if sai_comp:
        headers_saida = sheet_headers_for(sai_key, sai_cfg)
        try:
            ws_saida = get_worksheet(sai_cfg["sheet_name"], headers_saida)
            validas = linhas_validas(read_modality_rows(sai_cfg["sheet_name"], headers_saida))
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "carregar os inscritos")]}), 502
        alvo_saida = localizar_linha(validas, sai.get("row"), sai.get("id_inscricao"), sai.get("nome"))
        if alvo_saida is None:
            erros.append("Escolha quem está trocando (a lista pode ter mudado: recarregue a página).")
        elif _tem_resultado(alvo_saida):
            erros.append(f"{alvo_saida.get('nome')} já tem resultado em {sai_cfg['label']} — "
                         "quem já competiu não pode trocar.")
        else:
            pessoa = {k: alvo_saida.get(k, "") for k in ("nome", "telefone", "cla")}

    if entra_comp:
        nome = (entra.get("nome") or "").strip()
        telefone = (entra.get("telefone") or "").strip()
        cla = (entra.get("cla") or "").strip() if entra_cfg.get("collects_cla", True) else ""
        if not nome or not telefone_valido(telefone):
            erros.append("Informe nome e telefone com DDD de quem entra na competição.")
        pessoa_entrada = {"nome": nome, "telefone": telefone, "cla": cla}
    else:
        pessoa_entrada = None

    preco_sai = preco_de(sai_key, sai_modo) or 0
    preco_entra = preco_de(entra_key, entra_modo) or 0
    diferenca = round(max(0, preco_entra - preco_sai), 2)
    forma_diferenca = payload.get("forma_diferenca")
    if diferenca > 0 and forma_diferenca not in PAYMENT_OPTIONS:
        erros.append(f"A nova atividade é {format_brl(diferenca)} mais cara: informe como a diferença foi paga.")

    # No treino não dá para saber qual compra foi trocada, mas dá para
    # conferir se ainda existe alguma: o saldo (compras menos trocas já
    # feitas) daquela atividade e modo precisa ser maior que zero.
    if not sai_comp and not erros:
        try:
            esquecer_cache_aquisicao()
            saldo = sum(
                _inteiro(l["quantidade"]) or 0 for l in linhas_da_aquisicao()
                if l["atividade"] == sai_cfg["label"] and l["modo"] == sai_modo
            )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "errors": [mensagem_amigavel(exc, "conferir as compras")]}), 502
        if saldo <= 0:
            erros.append(f"Não há compra de {sai_cfg['label']} ({sai_modo}) disponível para trocar: "
                         "todas as que foram registradas já foram trocadas (ou nenhuma foi registrada).")
    if erros:
        return jsonify({"ok": False, "errors": erros}), 400

    rotulo_sai = f"{sai_cfg['label']} ({sai_modo})"
    rotulo_entra = f"{entra_cfg['label']} ({entra_modo})"
    observacao = f"Troca: {rotulo_sai} → {rotulo_entra}"
    if diferenca > 0:
        observacao += f"; diferença de {format_brl(diferenca)} paga em {forma_diferenca}"
    if preco_entra < preco_sai:
        observacao += "; nova atividade mais barata, sem devolução"

    id_entrada = f"{id_troca}-1" if entra_comp else ""
    comum = dict(
        id_compra=como_texto(id_troca),
        data_hora=agora_texto(),
        responsavel_nome=sanitize_cell(session.get("user_name", "")),
        responsavel_email=session.get("user_email", ""),
        situacao=SITUACAO_TROCA,
        observacao=observacao,
        assinatura="troca",
    )
    linhas = [
        montar_linha_aquisicao(
            **comum, atividade=sai_cfg["label"], modo=sai_modo, quantidade=-1,
            valor_unitario=_valor(preco_sai), valor_total=_valor(-preco_sai), forma_pagamento=FORMA_TROCA,
            nome_competidor=sanitize_cell(pessoa["nome"]), telefone_competidor=sanitize_cell(pessoa["telefone"]),
            cla_competidor=sanitize_cell(pessoa["cla"]),
            id_inscricao=como_texto((alvo_saida or {}).get("id_inscricao", "").strip()),
        ),
        montar_linha_aquisicao(
            **comum, atividade=entra_cfg["label"], modo=entra_modo, quantidade=1,
            valor_unitario=_valor(preco_entra), valor_total=_valor(preco_sai), forma_pagamento=FORMA_TROCA,
            nome_competidor=sanitize_cell((pessoa_entrada or {}).get("nome", "")),
            telefone_competidor=sanitize_cell((pessoa_entrada or {}).get("telefone", "")),
            cla_competidor=sanitize_cell((pessoa_entrada or {}).get("cla", "")),
            id_inscricao=como_texto(id_entrada),
        ),
    ]
    if diferenca > 0:
        linhas.append(montar_linha_aquisicao(
            **dict(comum, observacao=f"Diferença da troca {rotulo_sai} → {rotulo_entra}"),
            atividade=entra_cfg["label"], modo=entra_modo, quantidade=0,
            valor_unitario="", valor_total=_valor(diferenca), forma_pagamento=forma_diferenca,
        ))
    indice_diferenca = len(linhas) - 1 if diferenca > 0 else None

    try:
        ws = get_worksheet()
        if compra_existente(id_troca, ws) is not None:
            return jsonify({"ok": True, "id_troca": id_troca, "ja_registrada": True, "avisos": []})
        # Comprovante do PIX da diferença: opcional, como na Aquisição. Se
        # não chegar ao Drive, a troca é salva com "Imagem não recebida".
        if indice_diferenca is not None and forma_diferenca == "PIX" and foto and foto.filename:
            try:
                link = upload_photo_to_drive(foto, f"{id_troca}_diferenca", folder_id=DRIVE_FOLDER_ID)
            except Exception as exc:  # noqa: BLE001
                link = "Imagem não recebida"
                app.logger.error("Comprovante da troca %s não chegou ao Drive: %r", id_troca, exc)
            linhas[indice_diferenca][SHEET_HEADERS.index("link_foto")] = link
        tentar_google(ws.append_rows, linhas, value_input_option="USER_ENTERED", repetivel=False)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [
            mensagem_amigavel(exc, "registrar a troca"),
            "Pode tocar em Registrar de novo: se a troca tiver chegado, ela não será duplicada.",
        ]}), 502
    esquecer_cache_aquisicao()

    avisos = []
    if alvo_saida is not None:
        try:
            col_situacao = sheet_headers_for(sai_key, sai_cfg).index("situacao") + 1
            tentar_google(ws_saida.update, rowcol_to_a1(alvo_saida["_row"], col_situacao), [[SITUACAO_TROCOU]])
            esquecer_resultado(sai_key)
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Troca %s: não marquei 'trocou' em %s: %r", id_troca, sai_key, exc, exc_info=exc)
            avisos.append(f"A troca foi registrada, mas {pessoa['nome']} continua na lista de {sai_cfg['label']}: "
                          f"escreva \"{SITUACAO_TROCOU}\" na coluna situacao da linha {alvo_saida['_row']} "
                          f"da aba {sai_cfg['sheet_name']}.")
    if entra_comp:
        try:
            garantir_inscritos(entra_key, [dict(pessoa_entrada, id_inscricao=id_entrada)])
        except Exception as exc:  # noqa: BLE001
            app.logger.error("Troca %s: não incluí em %s: %r", id_troca, entra_key, exc, exc_info=exc)
            avisos.append(f"A troca foi registrada; {pessoa_entrada['nome']} vai aparecer na lista de "
                          f"{entra_cfg['label']} assim que o instrutor atualizar a página.")

    return jsonify({"ok": True, "id_troca": id_troca, "avisos": avisos})


def so_ddd(telefone):
    """Telefone completo -> só o DDD ("51 99999-8888" -> "51"). Aceita
    número com +55 na frente. Número incompleto (sem DDD claro) fica vazio."""
    if isinstance(telefone, float) and telefone.is_integer():
        telefone = int(telefone)  # a planilha pode devolver o número como 51999998888.0
    digitos = _digitos(telefone)
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        digitos = digitos[2:]
    if len(digitos) <= 2:
        return digitos  # já está só com o DDD (ou vazio)
    if len(digitos) >= 10:
        return digitos[:2]
    return ""


@app.route("/administracao/preparar-arquivo", methods=["POST"])
@exige("administracao")
def administracao_preparar_arquivo():
    """Deixa só o DDD nos telefones de todas as abas (v3), antes de fazer a
    cópia de arquivo do evento. Não dá para desfazer pelo app."""
    if (request.get_json(silent=True) or {}).get("confirmacao") != "ARQUIVAR":
        return jsonify({"ok": False, "errors": ["Digite ARQUIVAR para confirmar."]}), 400

    abas = [(NOME_ABA_AQUISICAO, SHEET_HEADERS, "telefone_competidor")]
    abas += [(ACTIVITIES[k]["sheet_name"], sheet_headers_for(k, ACTIVITIES[k]), "telefone") for k in TODOS_TORNEIOS]
    resumo, erros = [], []
    for nome_aba, headers, coluna in abas:
        try:
            ws = get_worksheet(nome_aba, headers)
            valores = tentar_google(ws.get_all_values, value_render_option="UNFORMATTED_VALUE")
            indice = headers.index(coluna)
            novos, alterados = [], 0
            for row in valores[1:]:
                atual = row[indice] if indice < len(row) else ""
                ddd = so_ddd(atual)
                alterados += ddd != str(atual)
                novos.append([ddd])
            if alterados:
                letra = letra_da_coluna(indice + 1)
                tentar_google(ws.update, f"{letra}2:{letra}{len(valores)}", novos, value_input_option="RAW")
            resumo.append({"aba": nome_aba, "alterados": alterados})
        except Exception as exc:  # noqa: BLE001
            erros.append(f"Aba {nome_aba}: {mensagem_amigavel(exc, 'preparar a aba')}")
    esquecer_cache_aquisicao()
    with _trava_cache_resultados:
        _cache_resultados.clear()
    return jsonify({"ok": not erros, "abas": resumo, "errors": erros}), (200 if not erros else 502)


# ---------------------------------------------------------------------------
# Outras rotas
# ---------------------------------------------------------------------------

@app.route("/saude")
def saude():
    """Rota levíssima (não fala com o Google) para um monitor externo chamar
    de tempos em tempos e impedir que o Render "adormeça" o serviço."""
    return "ok", 200


@app.route("/privacidade")
def privacidade():
    return render_template("privacidade.html")


@app.route("/termos")
def termos():
    return render_template("termos.html")


@app.errorhandler(404)
def erro_404(exc):
    return render_template("erro.html", codigo=404), 404


@app.errorhandler(413)
def erro_413(exc):
    mensagem = f"O arquivo enviado é grande demais (máximo de {MAX_UPLOAD_MB} MB). Tire outra foto e tente de novo."
    if request.method == "POST":
        return jsonify({"ok": False, "errors": [mensagem]}), 413
    return render_template("erro.html", codigo=413), 413


@app.errorhandler(500)
def erro_500(exc):
    # Rede de segurança geral: cobre qualquer falha que escape dos
    # try/except específicos de cada rota. Nos envios (POST), a tela espera
    # JSON, então a resposta vai em JSON com uma mensagem clara.
    app.logger.error("Erro inesperado em %s %s: %r", request.method, request.path, exc)
    if request.method == "POST":
        return jsonify({"ok": False, "errors": [
            "Aconteceu um erro inesperado no servidor. Tente de novo em alguns segundos; "
            "se continuar, avise a organização."
        ]}), 500
    return render_template("erro.html", codigo=500), 500


if __name__ == "__main__":
    # Só para rodar no seu computador. Sem o modo de depuração aberto para a
    # rede: com host 0.0.0.0, o depurador ficaria acessível no Wi-Fi.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="0.0.0.0", port=5000)
