# app.py
import os
import io
import uuid
import json
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from PIL import Image

try:
    # pillow-heif NÃO está no requirements.txt: no Windows local ele exige
    # compilar uma biblioteca nativa (MSYS2/toolchain C++) e trava a
    # instalação. No servidor (Render, Linux) existe pacote pronto, então
    # é instalado à parte, direto no Build Command do Render — ver README,
    # seção 6. Localmente, o app funciona normal sem essa lib (só não
    # comprime fotos .heic de iPhone; JPEG/PNG do Android não é afetado).
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
    COMPETITOR_SHEET_HEADERS,
    SWORDPLAY_HEADERS,
    TORNEIO_FISICOS,
    TORNEIO_CULTURAIS,
    score_headers,
)

# Lê as variáveis de um arquivo .env na mesma pasta, se ele existir — assim
# não é mais preciso rodar "export ..." toda vez que abrir um terminal novo.
# Se você continuar usando export manualmente, tudo bem também: load_dotenv()
# não sobrescreve uma variável que já foi exportada na sessão do terminal.
load_dotenv()

app = Flask(__name__)

# Sem isso, atrás de um proxy que termina HTTPS (ngrok, Render, etc.), o Flask
# "acha" que a conexão é HTTP simples — e o Google recusa gerar o botão de
# login com "Unsecured login_uri provided". O ProxyFix ensina o Flask a
# confiar nos cabeçalhos X-Forwarded-* que esses serviços enviam, então
# request.url_root passa a refletir corretamente o https:// externo.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not app.secret_key:
    # Sem FLASK_SECRET_KEY definido, as sessões de login não sobrevivem a um
    # reinício do servidor. Funciona para testar, mas defina essa variável
    # antes de colocar em produção (qualquer string longa e aleatória serve).
    app.secret_key = os.urandom(24)

MAX_PHOTO_SIZE_MB = 15
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}

# ---------------------------------------------------------------------------
# Login com Google (Google Identity Services)
# ---------------------------------------------------------------------------
#   GOOGLE_OAUTH_CLIENT_ID -> Client ID OAuth "Aplicativo da Web", criado no
#                             mesmo projeto do Google Cloud (é DIFERENTE da
#                             service account usada para Sheets/Drive).
#   ALLOWED_EMAILS         -> opcional; lista separada por vírgula de e-mails
#                             liberados a usar o app. Se vazio, qualquer conta
#                             Google pode entrar.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
ALLOWED_EMAILS = {
    e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()
}


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_email" not in session:
            if request.method == "GET":
                return redirect(url_for("login", next=request.path))
            return jsonify({"ok": False, "errors": ["Sessão expirada. Faça login novamente."]}), 401
        return view_func(*args, **kwargs)
    return wrapped

# ---------------------------------------------------------------------------
# Configuração Google (Sheets + Drive)
# ---------------------------------------------------------------------------
# Todas as credenciais vêm de variáveis de ambiente — nunca ficam no código.
#   GOOGLE_SERVICE_ACCOUNT_FILE  -> caminho para o .json da service account
#   GOOGLE_SHEET_ID              -> ID da planilha (está na URL do Sheets)
#   GOOGLE_DRIVE_FOLDER_ID       -> ID da pasta do Drive onde as fotos vão

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")

# Upload de fotos: NÃO usa a service account (contas de serviço não têm cota
# de armazenamento própria no Drive — só em Shared Drives, que exigem Google
# Workspace). Em vez disso, usa uma autorização OAuth feita uma única vez
# com a conta pessoal (rode setup_drive_auth.py). O token gerado por esse
# script fica salvo neste caminho:
GOOGLE_DRIVE_TOKEN_FILE = os.environ.get("GOOGLE_DRIVE_TOKEN_FILE", "drive_token.json")
DRIVE_UPLOAD_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_gspread_client = None
_drive_service = None


def get_gspread_client():
    """Cria (uma vez) e reaproveita o cliente do gspread (via service account —
    edição de uma planilha existente não exige cota de armazenamento)."""
    global _gspread_client
    if _gspread_client is None:
        import gspread
        from google.oauth2.service_account import Credentials

        if not SERVICE_ACCOUNT_FILE:
            raise RuntimeError(
                "A variável GOOGLE_SERVICE_ACCOUNT_FILE não está definida nesta sessão "
                "do terminal. Exporte o caminho do .json da service account e reinicie o app."
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
    """Cria (uma vez) e reaproveita o cliente do Google Drive, autenticado
    com a SUA conta pessoal (não a service account) — os uploads passam a
    usar o seu espaço normal do Drive."""
    global _drive_service
    if _drive_service is None:
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
            # Tenta salvar o token renovado de volta no arquivo, pra não
            # precisar renovar nas próximas vezes. Isso funciona localmente,
            # mas em servidores como o Render o arquivo pode estar montado
            # como "só leitura" (Secret Files) — nesse caso, ignoramos o
            # erro: a renovação já aconteceu na memória, e é suficiente
            # pra essa execução. Na próxima, o processo renova de novo a
            # partir do refresh_token original, que continua válido.
            try:
                with open(GOOGLE_DRIVE_TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except OSError:
                pass

        _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


_spreadsheet = None


def get_spreadsheet():
    """Abre (uma vez) e reaproveita o objeto da planilha mestra inteira."""
    global _spreadsheet
    if _spreadsheet is None:
        client = get_gspread_client()

        if not SHEET_ID:
            raise RuntimeError(
                "A variável GOOGLE_SHEET_ID não está definida nesta sessão do terminal."
            )

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


def get_worksheet(sheet_name=None, headers=None):
    """Abre uma aba da planilha mestra pelo nome (padrão: a aba da Aquisição)
    e garante que o cabeçalho dela existe."""
    sh = get_spreadsheet()
    sheet_name = sheet_name or NOME_ABA_AQUISICAO
    headers = headers or SHEET_HEADERS

    try:
        ws = sh.worksheet(sheet_name)
    except Exception as exc:
        raise RuntimeError(
            f"Não encontrei a aba '{sheet_name}' na planilha. Confira se o nome "
            f"está exatamente igual (maiúsculas e acentos importam). "
            f"Erro original: {exc}"
        ) from exc

    first_row = ws.row_values(1)
    if first_row != headers:
        ws.update("A1", [headers])
    return ws


def read_modality_rows(sheet_name, headers):
    """Lê todas as linhas de dados de uma aba de atividade, como lista de
    dicionários. Cada item inclui "_row" (número real da linha na planilha,
    contando o cabeçalho) — necessário pra depois atualizar aquela linha
    específica sem mexer nas demais."""
    ws = get_worksheet(sheet_name, headers)
    all_values = ws.get_all_values()
    result = []
    for row_number, row in enumerate(all_values[1:], start=2):
        padded = row + [""] * (len(headers) - len(row))
        item = dict(zip(headers, padded))
        item["_row"] = row_number
        result.append(item)
    return result


def ordenar_por_nome(rows):
    return sorted(rows, key=lambda r: r.get("nome", "").strip().lower())


# Fotos são redimensionadas e recomprimidas antes de subir pro Drive — o
# comprovante só precisa ser legível, não em alta resolução, e isso evita
# gastar o espaço do Drive à toa (fotos de celular fácil passam de 5-8MB).
MAX_PHOTO_DIMENSION = 1600   # pixels no lado maior
TARGET_PHOTO_BYTES = 700_000  # ~0,7MB de alvo (bem abaixo de 1MB)
MIN_JPEG_QUALITY = 35         # não comprime além disso, pra manter legível


def compress_photo(file_bytes):
    """Redimensiona e comprime a foto para JPEG, mirando ~0,7MB.
    Se não conseguir processar a imagem (formato inesperado, arquivo
    corrompido etc.), devolve os bytes originais sem modificar — o envio
    não trava por causa da compressão."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = img.convert("RGB")  # remove transparência/CMYK, garante JPEG válido
    except Exception:
        return file_bytes, None

    img.thumbnail((MAX_PHOTO_DIMENSION, MAX_PHOTO_DIMENSION), Image.LANCZOS)

    quality = 85
    data = file_bytes
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= TARGET_PHOTO_BYTES or quality <= MIN_JPEG_QUALITY:
            break
        quality -= 10

    return data, "jpg"


def upload_photo_to_drive(file_storage, purchase_id):
    """Sobe a foto para o Drive (já comprimida) e devolve um link visualizável."""
    from googleapiclient.http import MediaIoBaseUpload

    service = get_drive_service()
    original_ext = file_storage.filename.rsplit(".", 1)[-1].lower()

    file_bytes = file_storage.read()
    compressed_bytes, new_ext = compress_photo(file_bytes)

    ext = new_ext or original_ext
    mimetype = "image/jpeg" if new_ext else file_storage.mimetype
    filename = f"{purchase_id}.{ext}"

    media = MediaIoBaseUpload(io.BytesIO(compressed_bytes), mimetype=mimetype, resumable=False)

    file_metadata = {"name": filename}
    if DRIVE_FOLDER_ID:
        file_metadata["parents"] = [DRIVE_FOLDER_ID]

    created = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = created["id"]

    # Torna o arquivo visualizável por quem tem o link (ajuste conforme a política da equipe)
    service.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}
    ).execute()

    return f"https://drive.google.com/file/d/{file_id}/view"


def format_brl(value):
    """Formata um número como moeda brasileira: 1234.5 -> 'R$ 1.234,50'. None vira ''."""
    if value is None:
        return ""
    texto = f"{value:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

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

        modo_efetivo = item.get("modo") or cfg.get("fixed_mode")
        requires_names = cfg.get("collects_competitor_names") and modo_efetivo == "Competição"
        if requires_names:
            raw_competidores = item.get("competidores") or []
            competidores = []
            for c in raw_competidores:
                if not isinstance(c, dict):
                    continue
                nome = (c.get("nome") or "").strip()
                telefone = (c.get("telefone") or "").strip()
                cla = (c.get("cla") or "").strip()  # opcional — pode ficar em branco
                if not nome or not telefone:
                    continue
                digitos = "".join(ch for ch in telefone if ch.isdigit())
                if len(digitos) < 10 or len(digitos) > 11:
                    errors.append(
                        f"Telefone de '{nome}' em {label} parece incompleto — "
                        f"inclua o DDD (ex.: 51999998888)."
                    )
                    continue
                competidores.append({"nome": nome, "telefone": telefone, "cla": cla})

            item["competidores"] = competidores  # normaliza pro resto do código usar
            if isinstance(quantidade, int) and quantidade > 0:
                if len(competidores) != quantidade:
                    errors.append(
                        f"Informe nome e telefone (com DDD) de cada competidor de {label} "
                        f"({quantidade} esperado(s), {len(competidores)} completo(s))."
                    )

    return errors


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

def safe_redirect_target(default_endpoint):
    """Evita redirecionamento aberto: só aceita caminhos internos (começando
    com '/', mas nunca '//', que poderia apontar pra fora do site)."""
    next_url = request.args.get("next") or request.form.get("next")
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
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

    email = (idinfo.get("email") or "").lower()
    name = idinfo.get("name", email)

    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return redirect(url_for("login", error="Este e-mail não tem acesso liberado para o app."))

    session["user_email"] = email
    session["user_name"] = name
    return redirect(safe_redirect_target("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/competicoes")
def competicoes():
    itens = [(key, ACTIVITIES[key]) for key in TORNEIO_FISICOS]
    return render_template("competicoes_hub.html", itens=itens)


@app.route("/competicoes/swordplay")
def competicao_swordplay():
    cfg = ACTIVITIES["swordplay"]
    erro = None
    try:
        rows = ordenar_por_nome(read_modality_rows(cfg["sheet_name"], SWORDPLAY_HEADERS))
    except Exception as exc:  # noqa: BLE001
        rows = []
        erro = str(exc)
    return render_template("swordplay.html", cfg=cfg, rows=rows, erro=erro)


@app.route("/competicoes/swordplay", methods=["POST"])
def competicao_swordplay_enviar():
    from gspread.utils import rowcol_to_a1

    payload = request.get_json(silent=True) or {}
    posicoes = payload.get("posicoes")
    if not isinstance(posicoes, list):
        return jsonify({"ok": False, "errors": ["Dados inválidos."]}), 400

    cfg = ACTIVITIES["swordplay"]
    atualizados = 0
    try:
        ws = get_worksheet(cfg["sheet_name"], SWORDPLAY_HEADERS)
        for item in posicoes:
            posicao = item.get("posicao")
            row_number = item.get("row")
            # Ignora quem não tem posição preenchida — não sobrescreve com vazio.
            if posicao in (None, "") or not isinstance(row_number, int) or row_number < 2:
                continue
            try:
                posicao_num = int(posicao)
            except (TypeError, ValueError):
                continue
            cell = rowcol_to_a1(row_number, len(SWORDPLAY_HEADERS))  # coluna "posicao"
            ws.update(cell, [[posicao_num]], value_input_option="USER_ENTERED")
            atualizados += 1
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [f"Erro ao gravar as posições: {exc}"]}), 502

    return jsonify({"ok": True, "atualizados": atualizados})


@app.route("/competicoes/<key>")
def competicao_pontuar(key):
    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TORNEIO_FISICOS or not cfg.get("num_tiros"):
        return redirect(url_for("competicoes"))

    headers = score_headers(cfg["num_tiros"])
    erro = None
    try:
        rows = ordenar_por_nome(read_modality_rows(cfg["sheet_name"], headers))
    except Exception as exc:  # noqa: BLE001
        rows = []
        erro = str(exc)

    return render_template(
        "competicao_pontuar.html",
        cfg=cfg,
        key=key,
        rows=rows,
        tiro_indices=list(range(1, cfg["num_tiros"] + 1)),
        erro=erro,
    )


@app.route("/competicoes/<key>/pontuar", methods=["POST"])
def competicao_enviar_nota(key):
    from gspread.utils import rowcol_to_a1

    cfg = ACTIVITIES.get(key)
    if not cfg or key not in TORNEIO_FISICOS or not cfg.get("num_tiros"):
        return jsonify({"ok": False, "errors": ["Atividade inválida."]}), 400

    payload = request.get_json(silent=True) or {}
    row_number = payload.get("row")
    tiros = payload.get("tiros")

    if not isinstance(row_number, int) or row_number < 2:
        return jsonify({"ok": False, "errors": ["Linha inválida — atualize a página (F5) e tente de novo."]}), 400
    if not isinstance(tiros, list) or len(tiros) != cfg["num_tiros"]:
        return jsonify({"ok": False, "errors": [f"Informe as {cfg['num_tiros']} notas."]}), 400

    valores = []
    for v in tiros:
        try:
            n = float(v)
            if n < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"ok": False, "errors": ["Cada nota precisa ser um número válido (0 ou mais)."]}), 400
        valores.append(n)

    total = round(sum(valores), 2)
    headers = score_headers(cfg["num_tiros"])

    try:
        ws = get_worksheet(cfg["sheet_name"], headers)
        start_col = 4  # coluna D: logo após nome/cla/telefone
        end_col = start_col + len(valores)  # coluna do total
        start_a1 = rowcol_to_a1(row_number, start_col)
        end_a1 = rowcol_to_a1(row_number, end_col)
        ws.update(f"{start_a1}:{end_a1}", [valores + [total]], value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "errors": [f"Erro ao gravar a nota: {exc}"]}), 502

    return jsonify({"ok": True, "total": total})


@app.route("/resultados")
def resultados():
    fisicos = [(key, ACTIVITIES[key]) for key in TORNEIO_FISICOS]
    culturais = [(key, ACTIVITIES[key]) for key in TORNEIO_CULTURAIS]
    return render_template("resultados_hub.html", fisicos=fisicos, culturais=culturais)


@app.route("/resultados/<key>")
def resultado_atividade(key):
    cfg = ACTIVITIES.get(key)
    if not cfg:
        return redirect(url_for("resultados"))

    erro = None

    if key in TORNEIO_CULTURAIS:
        try:
            rows = ordenar_por_nome(read_modality_rows(cfg["sheet_name"], COMPETITOR_SHEET_HEADERS))
        except Exception as exc:  # noqa: BLE001
            rows, erro = [], str(exc)
        return render_template("resultado_cultural.html", cfg=cfg, rows=rows, erro=erro)

    if key == "swordplay":
        try:
            rows = read_modality_rows(cfg["sheet_name"], SWORDPLAY_HEADERS)
        except Exception as exc:  # noqa: BLE001
            rows, erro = [], str(exc)
        else:
            def posicao_key(r):
                try:
                    return int(r["posicao"])
                except (TypeError, ValueError):
                    return 999999
            rows = [r for r in rows if r.get("posicao")]
            rows.sort(key=posicao_key)
        return render_template("resultado_torneio.html", cfg=cfg, top3=rows[:3], erro=erro)

    if cfg.get("num_tiros"):
        headers = score_headers(cfg["num_tiros"])
        try:
            rows = read_modality_rows(cfg["sheet_name"], headers)
        except Exception as exc:  # noqa: BLE001
            rows, erro = [], str(exc)
        else:
            def total_key(r):
                try:
                    return float(r["total"])
                except (TypeError, ValueError):
                    return -1
            rows = [r for r in rows if r.get("total")]
            rows.sort(key=total_key, reverse=True)
        return render_template("resultado_torneio.html", cfg=cfg, top3=rows[:3], erro=erro)

    return redirect(url_for("resultados"))


@app.route("/aquisicao")
@login_required
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


@app.route("/submit", methods=["POST"])
@login_required
def submit():
    try:
        activities_payload = json.loads(request.form.get("activities_json", "[]"))
    except json.JSONDecodeError:
        return jsonify({"ok": False, "errors": ["Dados do formulário corrompidos. Tente novamente."]}), 400

    photo_file = request.files.get("photo")
    forma_pagamento = request.form.get("forma_pagamento", "")
    responsavel_nome = session.get("user_name", "")
    responsavel_email = session.get("user_email", "")

    errors = validate_submission(activities_payload, photo_file, forma_pagamento)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    purchase_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    photo_link = ""
    if photo_file and photo_file.filename:
        try:
            photo_link = upload_photo_to_drive(photo_file, purchase_id)
        except Exception as exc:  # noqa: BLE001 — captura qualquer falha do Google
            return jsonify({
                "ok": False,
                "errors": [f"Não foi possível enviar a foto ao Google Drive: {exc}"],
            }), 502

    rows = []
    competitor_rows_by_sheet = {}
    for item in activities_payload:
        cfg = ACTIVITIES[item["activity"]]
        modo = cfg["fixed_mode"] or item.get("modo", "")
        quantidade = int(item["quantidade"])

        raw_preco = cfg.get("preco_unitario")
        preco_unitario = raw_preco.get(modo) if isinstance(raw_preco, dict) else raw_preco
        valor_unitario = format_brl(preco_unitario)

        competidores = item.get("competidores") or []

        if competidores:
            # Uma linha por competidor, mesmo que comprados juntos — cada linha
            # com quantidade 1, pra não contar errado ao somar a coluna quantidade.
            for competidor in competidores:
                rows.append([
                    purchase_id,
                    timestamp,
                    cfg["label"],
                    modo,
                    1,
                    valor_unitario,
                    valor_unitario,  # quantidade 1 nessa linha, então total = unitário
                    forma_pagamento,
                    competidor["nome"],
                    competidor["telefone"],
                    competidor["cla"],
                    photo_link,
                    responsavel_nome,
                    responsavel_email,
                ])

            # Também prepara a cópia pra aba própria da atividade (nome/clã/
            # telefone), pra já chegar pronta pro instrutor pontuar depois.
            sheet_name = cfg.get("sheet_name")
            if sheet_name:
                competitor_rows_by_sheet.setdefault(sheet_name, []).extend(
                    [c["nome"], c["cla"], c["telefone"]] for c in competidores
                )
        else:
            valor_total = format_brl(round(preco_unitario * quantidade, 2)) if preco_unitario is not None else ""
            rows.append([
                purchase_id,
                timestamp,
                cfg["label"],
                modo,
                quantidade,
                valor_unitario,
                valor_total,
                forma_pagamento,
                "",
                "",
                "",
                photo_link,
                responsavel_nome,
                responsavel_email,
            ])

    try:
        ws = get_worksheet()
        ws.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        detalhe = "A foto foi enviada, mas" if photo_link else "Os dados foram validados, mas"
        return jsonify({
            "ok": False,
            "errors": [f"{detalhe} houve um erro ao gravar na planilha: {exc}"],
        }), 502

    # Copia os competidores pras abas de cada atividade (arco_flecha, machado,
    # swordplay, vestimenta, bardos, feiticos). A compra já foi salva com
    # sucesso acima — se isso aqui falhar (ex.: aba não existe ainda), a
    # compra continua válida, só avisa em vez de travar o envio.
    avisos = []
    for sheet_name, comp_rows in competitor_rows_by_sheet.items():
        try:
            modality_ws = get_worksheet(sheet_name, COMPETITOR_SHEET_HEADERS)
            modality_ws.append_rows(comp_rows, value_input_option="USER_ENTERED")
        except Exception as exc:  # noqa: BLE001
            avisos.append(
                f"A compra foi salva, mas não consegui copiar os competidores "
                f"para a aba '{sheet_name}': {exc}"
            )

    return jsonify({"ok": True, "purchase_id": purchase_id, "avisos": avisos})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
