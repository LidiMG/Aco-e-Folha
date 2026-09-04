"""
Rode este script UMA VEZ, localmente, para autorizar o app a enviar fotos
para o SEU Google Drive pessoal (em vez da conta de serviço, que não tem
espaço de armazenamento próprio).

Isso abre uma janela do navegador pedindo pra você entrar com a conta
Google e confirmar a permissão. Depois de autorizar, gera um arquivo
drive_token.json — é ele que o app usa a partir de então para enviar fotos,
sem precisar repetir esse processo (a menos que você revogue o acesso).

Pré-requisito: um OAuth Client ID do tipo "Aplicativo para computador"
(Desktop app) — diferente do que você já criou para o login da equipe, que
era "Aplicativo da Web". Baixe o JSON dessas credenciais no Google Cloud
Console e salve como client_secret.json, nesta mesma pasta.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "drive_token.json"


def main():
    if not os.path.exists(CLIENT_SECRET_FILE):
        raise SystemExit(
            f"Não encontrei '{CLIENT_SECRET_FILE}' nesta pasta.\n"
            "No Google Cloud Console → Credenciais → Criar credenciais → "
            "ID do cliente OAuth → tipo 'Aplicativo para computador'.\n"
            f"Baixe o JSON gerado e salve exatamente como '{CLIENT_SECRET_FILE}' aqui."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"\nPronto! Autorização salva em '{TOKEN_FILE}'.")
    print("Isso já é lido automaticamente pelo app (GOOGLE_DRIVE_TOKEN_FILE aponta")
    print(f"para '{TOKEN_FILE}' por padrão). Reinicie o app e teste o envio de uma foto.")
    print("\nIMPORTANTE: nunca suba client_secret.json nem drive_token.json pro GitHub.")


if __name__ == "__main__":
    main()
