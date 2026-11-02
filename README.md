# Aço & Folha — Sistema de Gestão do Evento

**Versão 3** — preparada para o próximo evento a partir de uma revisão
completa da versão 2 (ver seção "Histórico de versões", no fim deste
arquivo).

Este projeto foi desenvolvido para o evento **Aço & Folha**, para dar conta
de três frentes que antes seriam planilhas separadas e soltas: registrar as
compras de atividades, lançar os resultados dos torneios físicos
(Arco e Flecha, Arremesso de Machado, Swordplay, Rachar Lenha) e acompanhar
as atividades culturais (Vestimenta, Bardos, Feitiços, Beberrão).

É um app web mobile (instalável como PWA), sem custo de hospedagem paga
obrigatório, e sem depender de planilhas soltas e desencontradas — tudo
alimenta a mesma planilha Google Sheets, e boa parte se alimenta sozinha.

> Este projeto foi **construído inteiramente pela Claude AI (Anthropic)**,
> a partir das orientações, decisões e testes de Lidiane Gomes — que
> conduziu cada etapa (o que construir, em que ordem, com quais regras de
> negócio conforme orientação dos organizadores do evento), mas a escrita do código, a arquitetura técnica e a maior parte
> das soluções de UI foram trabalho do Claude.

---

## 1. O que o app faz

O app tem uma tela inicial com três caminhos (e um quarto, só para a
administração):

- **Aquisições** (`/aquisicao`, exige login com Google e o código da
  equipe) — a equipe de
  atendimento registra cada compra: foto do comprovante (opcional),
  atividades e quantidades (com preço calculado automaticamente), forma de
  pagamento, e nome/telefone/clã de quem vai competir, quando aplicável.
  Tudo isso vira uma linha na planilha, por atividade.
- **Competições** (`/competicoes`, exige o código da equipe) — organizada
  em Torneios e Atividades Culturais. Os instrutores lançam os resultados:
  quadrados de pontuação (de 0 a 10) mais a foto final do alvo
  (obrigatória) para Arco e Flecha/Arremesso de Machado, e a posição final
  no ranking para Swordplay, Rachar Lenha e todas as culturais. A
  organização também corrige notas por aqui.
- **Resultados** (`/resultados`, aberto) — o Top 3 de cada torneio e de
  cada atividade cultural, calculado automaticamente a partir do que foi
  lançado em Competições, com os empates indicados. É aqui, junto das
  fotos dos alvos, que a organização registra os desempates.
- **Administração** (`/administracao`, só para o e-mail da administração)
  — resumo do evento (totais), trocas de atividade e o preparo da
  planilha para arquivo depois do evento (seção 10.2).

### Mapa do sistema (PDF)

O arquivo `mapa_do_sistema.pdf`, incluído neste repositório, tem os
diagramas da estrutura completa do app — a tela inicial e os três modos,
com o fluxo de dentro de cada um (Aquisição, Competições e Resultados).
Serve como um guia visual rápido para quem estiver sendo treinado para
usar o app — ajuda a entender de cara "quem faz o quê, onde" sem precisar
ler este README inteiro. Está atualizado com as telas da v3 (código da
equipe, Administração, correção de nota e desempate).

## 2. Estrutura do projeto

```
evento-app/
├── app.py                     # Flask: rotas, validação, integração Google
├── config.py                  # Atividades, preços, ícones — edite aqui para mudar o "cardápio"
├── setup_drive_auth.py        # Script de autorização única do Drive (rodar localmente)
├── requirements.txt
├── requirements-dev.txt        # Só para rodar os testes (pytest)
├── .env.example                # Modelo do .env — copie e preencha
├── mapa_do_sistema.pdf         # Diagramas da estrutura do app — bom para treinar gente nova
├── tests/                      # Testes automáticos com planilha simulada (v3)
│   ├── conftest.py
│   └── test_app.py
├── .github/workflows/testes.yml # Roda os testes no GitHub a cada push (v3)
├── templates/
│   ├── home.html               # Tela inicial (hub dos modos)
│   ├── login.html               # Login com Google (Aquisição, organização, administração)
│   ├── entrar_equipe.html       # Código da equipe (v3)
│   ├── administracao.html       # Área da administração (v3)
│   ├── index.html                # Formulário de Aquisição
│   ├── competicoes_hub.html      # Hub de Competições (Torneios e Atividades Culturais)
│   ├── competicao_pontuar.html   # Lançamento de notas (Arco/Machado)
│   ├── competicao_ranking.html   # Lançamento de posição (Swordplay, Rachar Lenha, culturais)
│   ├── resultados_hub.html       # Hub de Resultados
│   ├── resultado_torneio.html    # Top 3 de cada atividade + desempate (organização)
│   ├── privacidade.html          # Política de Privacidade (link p/ OAuth em produção)
│   ├── termos.html                # Termos de Serviço (idem)
│   ├── erro.html                  # Página 404/500 amigável (rede de segurança geral)
│   └── coming_soon.html          # Template genérico "em construção" (reserva)
└── static/
    ├── style.css
    ├── app.js                    # Lógica da tela de Aquisição
    ├── fotos.js                  # Compressão da foto no próprio celular (v2)
    ├── rede.js                   # Envio ao servidor com tratamento de erros (v2)
    ├── competicoes.js            # Lógica das telas de Competições
    ├── admin.js                  # Lógica da Administração (v3)
    ├── resultados.js             # Desempate em Resultados (v3)
    ├── manifest.json
    ├── service-worker.js         # Servido na raiz do site, em /service-worker.js (v3)
    ├── icon-192.png / icon-512.png             # ícone "any" (iPhone/Windows/Mac)
    ├── icon-192-maskable.png / icon-512-maskable.png  # ícone "maskable" (Android)
    └── img/hero-aco-folha.jpg    # Imagem de topo da tela inicial
```

## 3. Configurar a conta Google (uma vez só)

Você vai testar primeiro com `seuemail@gmail.com`, depois repete o mesmo
processo com a conta oficial da equipe quando for para produção.

1. **Criar um projeto no Google Cloud**
   Acesse [console.cloud.google.com](https://console.cloud.google.com/),
   crie um projeto novo (ex.: "evento-app").

2. **Ativar as APIs necessárias**
   No menu "APIs e serviços" → "Biblioteca", ative:
   - Google Sheets API
   - Google Drive API

3. **Criar as credenciais do Google Cloud** (são duas, nesta ordem)
   **Parte A — Service Account** (para gravar na planilha/Drive):
   "APIs e serviços" → "Credenciais" → "Criar credenciais" → "Conta de serviço".
   Dê um nome (ex.: `evento-app-bot`) e conclua. Depois, na conta de serviço
   criada, vá em "Chaves" → "Adicionar chave" → "Criar nova chave" → JSON.
   Isso baixa um arquivo `.json` — **guarde-o fora do controle de versão**
   (nunca suba esse arquivo para o GitHub).
   **Parte B — OAuth Client ID** (para o login "Entrar com Google" da
   equipe): uma credencial diferente da Service Account — é ela que
   permite que cada pessoa da equipe entre com a própria conta.
   "APIs e serviços" → "Credenciais" → "Criar credenciais" →
   "ID do cliente OAuth" → tipo "Aplicativo da Web".
   Em "Origens JavaScript autorizadas", adicione a URL onde o app vai
   rodar (ex.: `http://localhost:5000` para testar local, e depois a URL
   real depois do deploy, tipo `https://evento-app.onrender.com`).
   Copie o **Client ID** gerado (algo como `123...apps.googleusercontent.com`).

4. **Compartilhar a planilha com a service account**
   O arquivo `.json` da service account tem um campo `client_email`
   (algo como `evento-app-bot@evento-app.iam.gserviceaccount.com`).
   Crie uma planilha Google Sheets, com abas para `aquisicao`,
   `arco_flecha`, `machado`, `swordplay`, `rachar_lenha`, `vestimenta`,
   `bardos`, `feiticos` e `beberrao` (os nomes exatos ficam configurados
   em `config.py`), e compartilhe a planilha inteira com esse e-mail como
   **Editor**. Copie o ID da planilha (fica na URL, entre `/d/` e `/edit`).

5. **Autorizar o upload de fotos com a sua conta pessoal**
   Diferente da planilha, o Drive **não aceita** que a service account
   crie arquivos novos — ela não tem espaço de armazenamento próprio (isso
   só existe em Shared Drives, recurso de contas Workspace pagas). Por
   isso os uploads de foto usam uma autorização separada, feita uma única
   vez com a sua própria conta:

   1. No Google Cloud Console → Credenciais → "Criar credenciais" →
      "ID do cliente OAuth" → tipo **"Aplicativo para computador"**
      (não é o mesmo tipo usado no login da equipe, que é "Aplicativo
      da Web").
   2. Baixe o JSON gerado, salve como `client_secret.json` dentro da
      pasta `evento-app/`.
   3. Rode `python setup_drive_auth.py` — abre uma janela do navegador
      pedindo para você entrar e autorizar. Ao concluir, gera um
      `drive_token.json` na mesma pasta.
   4. Pronto — o app já lê esse arquivo automaticamente daqui para frente.
      Você só precisa repetir isso se revogar o acesso ou trocar de conta.

   As fotos vão para a raiz do seu Drive por padrão, a não ser que você
   defina `GOOGLE_DRIVE_FOLDER_ID` (veja o passo 4) apontando para uma
   pasta específica sua.

   ⚠️ **Enquanto o projeto estiver em modo "Teste"** no Google Cloud
   (padrão), essa autorização expira a cada **7 dias** — os uploads de
   foto param de funcionar até você rodar `python setup_drive_auth.py`
   de novo. Não afeta o login da equipe (isso é isento dessa regra).
   Se isso incomodar no futuro, dá para resolver de vez publicando o
   projeto como "Em produção" na tela de permissão OAuth do Google Cloud.

## 4. Configurar o ambiente local

```bash
cd evento-app
python -m venv venv
source venv/bin/activate      # no Git Bash / Windows: source venv/Scripts/activate
pip install -r requirements.txt
```

Copie `.env.example` para um novo arquivo chamado `.env`, na mesma pasta,
e preencha com os seus valores:

```
GOOGLE_SERVICE_ACCOUNT_FILE=/caminho/para/sua-chave.json
GOOGLE_SHEET_ID=id_da_planilha
GOOGLE_DRIVE_FOLDER_ID=id_da_pasta_dos_comprovantes
GOOGLE_DRIVE_ALVOS_FOLDER_ID=id_da_pasta_das_fotos_dos_alvos
GOOGLE_OAUTH_CLIENT_ID=123...apps.googleusercontent.com
GOOGLE_DRIVE_TOKEN_FILE=drive_token.json
FLASK_SECRET_KEY=uma-string-longa-e-aleatoria-qualquer
CODIGO_EQUIPE=
EMAIL_ORGANIZACAO=organizador@gmail.com
EMAIL_ADMINISTRACAO=seuemail@gmail.com
ALLOWED_EMAILS=
```

As três variáveis de acesso (`CODIGO_EQUIPE`, `EMAIL_ORGANIZACAO` e
`EMAIL_ADMINISTRACAO`) estão explicadas na seção 7. Localmente, deixar
`CODIGO_EQUIPE` vazio faz o app não pedir código nenhum.

**Duas pastas no Drive, com acessos diferentes (v2):**

- `GOOGLE_DRIVE_FOLDER_ID` — comprovantes de PIX. **Privada**: os
  comprovantes têm dados pessoais e bancários, então só quem tem acesso à
  pasta consegue abri-los. Para outras pessoas da organização verem,
  compartilhe a pasta com o e-mail de cada uma (não com "qualquer pessoa
  com o link").
- `GOOGLE_DRIVE_ALVOS_FOLDER_ID` — fotos finais dos alvos (Arco e
  Machado). **Pode ficar privada**: a tela de Resultados não abre o link
  do Drive, e sim a rota `/resultados/foto/<id>`, em que o próprio app
  busca a foto com a autorização que já tem e entrega a imagem — sem
  pedir login Google a quem está olhando. Essa rota só entrega arquivos
  desta pasta, nunca comprovantes de PIX.

O app lê esse arquivo sozinho toda vez que inicia — não precisa de
`export` nenhum, em nenhum terminal, nunca mais. O `.env` já está
protegido no `.gitignore`, então não corre risco de subir para o Git por
engano.

## 5. Rodar localmente

```bash
python app.py
```

O servidor sobe em `http://0.0.0.0:5000`. Para testar **no celular Android**
enquanto ainda está rodando só no seu computador:

1. Confirme que o celular está na **mesma rede Wi-Fi** do computador.
2. Descubra o IP local do computador (`ipconfig` no Windows, procure por
   "Endereço IPv4").
3. No navegador do celular, acesse `http://SEU_IP_LOCAL:5000`.
4. No Chrome do Android, use o menu "⋮" → "Adicionar à tela inicial" para
   instalar como app (isso é o que o `manifest.json` habilita).

**Importante:** o login com Google exige HTTPS em qualquer endereço que não
seja `localhost` — pelo IP da rede local, o botão de login não aparece. Pra
testar o login de verdade no celular, use um túnel como o
[ngrok](https://ngrok.com/) (`ngrok http 5000`), e adicione a URL gerada
nas "Origens JavaScript autorizadas" do Client ID (passo 3, Parte B).

## 6. Colocar no ar para a equipe usar de verdade

Rodar só no seu computador não é viável no dia do evento. O projeto está
hospedado gratuitamente no **Render** (plano Free, sem domínio próprio —
o link definitivo é do tipo `https://SEU-SERVICO.onrender.com`).

- **Build Command**: `pip install -r requirements.txt` — desde a v3, o
  `pillow-heif` (que permite abrir fotos `.heic` de iPhone) está no
  `requirements.txt`, com a versão fixada e uma condição que faz ele ser
  instalado **só no Linux**: no Render ele entra; no Windows local ele é
  pulado (lá ele exigiria compilar C++ e travaria a instalação). Antes, o
  Build Command instalava a versão mais nova a cada deploy, e uma versão
  nova com problema poderia quebrar o deploy na véspera do evento. O
  Build Command antigo (`... && pip install pillow-heif`) continua
  funcionando, mas pode ser simplificado.
- **Start Command**: `gunicorn app:app --workers 2 --threads 4 --timeout 45`
  — 2 processos com 4 linhas de atendimento cada, ou seja, até 8 envios
  ao mesmo tempo. Na v1 eram 3 processos simples, e no evento, com umas 5
  pessoas enviando juntas, formava fila: como cada envio passa a maior
  parte do tempo só esperando o Google responder, as threads aproveitam
  essa espera sem gastar mais memória. Com threads, o `--timeout 45` só
  reinicia um processo realmente travado — ele **não** interrompe um
  envio lento. Quem limita o tempo de cada envio é o tempo-limite de rede
  (abaixo) e, na compra, o prazo de 35 segundos da seção 9.
- **Tempo-limite de rede no próprio código**: `socket.setdefaulttimeout(25)`
  no topo do `app.py` garante que uma chamada ao Google (Sheets, Drive,
  verificação de login) que travar falha sozinha em 25s — dentro do
  try/except de cada rota, mostrando um erro decente — em vez de ficar
  pendurada até o gunicorn cortar o processo (que aí sim gera um 500 sem
  mensagem nenhuma para quem está usando).
- **Variáveis de acesso (v3)**: em Environment, crie `CODIGO_EQUIPE`,
  `EMAIL_ORGANIZACAO` e `EMAIL_ADMINISTRACAO` (seção 7). Sem
  `CODIGO_EQUIPE`, Competições e Aquisição ficam sem código.
- **Manter o serviço acordado**: ver "Monitor UptimeRobot", logo abaixo.
- **Plano Free**: o serviço "dorme" depois de 15 minutos sem acesso, e
  demora uns 30-60 segundos para acordar no primeiro acesso seguinte —
  isso é normal, não é erro. Ficar dias sem uso não tem problema nenhum,
  nem risco do serviço ser apagado por inatividade.
- Alternativas equivalentes, caso o Render dê algum problema no futuro:
  **Railway** (mesma lógica de Git + variáveis de ambiente) ou
  **PythonAnywhere** (mais simples ainda, sem lidar com `gunicorn`).

### Monitor UptimeRobot (manter o serviço acordado)

No plano gratuito, o Render "adormece" o serviço depois de 15 minutos
sem acesso, e o primeiro acesso seguinte demora 30-60 segundos. Para que
ninguém espere isso no dia do evento, um monitor gratuito do
[UptimeRobot](https://uptimerobot.com) chama a rota `/saude` a cada 5
minutos. Essa rota responde só "ok" e não fala com o Google.

Como configurar:

1. Abra `https://SEU-SERVICO.onrender.com/saude` no navegador e confira
   que aparece "ok".
2. No UptimeRobot, crie um monitor novo ("+ Add New Monitor") do tipo
   **HTTP / website monitoring** (na interface nova ele é o tipo padrão:
   a tela já começa pedindo a URL). Tipos **Ping** e **Port** não servem,
   porque não abrem a página e o serviço continua adormecendo.
3. URL: `https://SEU-SERVICO.onrender.com/saude`. Intervalo: **5
   minutos**. Deixe o e-mail da organização nos alertas, para saber se o
   app sair do ar.
4. Para confirmar que está funcionando, abra os **Logs** do serviço no
   Render: devem aparecer linhas `GET /saude` a cada 5 minutos.

Custos: nenhum. O plano gratuito do UptimeRobot cobre esse uso; a banda
gasta pela rota é irrelevante (cerca de 2MB por mês); e as 750 horas
mensais do plano gratuito do Render cobrem um serviço acordado o mês
inteiro. Atenção só se houver **outros serviços gratuitos na mesma conta
do Render**: as 750 horas são divididas entre todos, e se estourarem o
Render suspende os serviços até o mês virar (sem cobrar nada).

### Entre um evento e outro: suspender e retomar

O serviço fica desligado entre os eventos e é religado no mês do próximo.

- **Desligar (depois do evento)**: primeiro **pause o monitor** no
  UptimeRobot (senão ele manda e-mails de alerta), depois suspenda o
  serviço no Render: na lista de serviços, marque o serviço e clique em
  **Suspend**, ou entre no serviço → **Settings** → no fim da página,
  **Suspend Web Service**. Cuidado para não clicar em **Delete**, logo ao
  lado, que apaga o serviço de vez.
- **Religar (antes do evento)**: no mesmo lugar, **Resume**; espere o
  serviço subir, confira `/saude` no navegador e só então **reative o
  monitor**. Troque também o `CODIGO_EQUIPE` (Environment) e combine o
  código novo com a equipe. Variáveis de ambiente, Secret Files e Start Command ficam
  guardados enquanto o serviço está suspenso — não precisa refazer nada.
- **Na volta, antes do evento**, vale também rodar
  `python setup_drive_auth.py` se o upload de fotos falhar (token do
  Drive revogado ou trocado de conta) e colar o `drive_token.json` novo no
  Secret File do Render.

### E os arquivos de credenciais (o `.json` da service account e o `drive_token.json`)?

Eles estão no `.gitignore` de propósito — nunca devem ir para o Git, nem
em repositório privado. Isso significa que um deploy via Git **não leva
esses arquivos junto**, então é preciso colocá-los no servidor por um
caminho separado. Note que só esses dois arquivos precisam estar no
servidor — o `client_secret.json` é usado só localmente, uma vez, pelo
`setup_drive_auth.py`, e nunca precisa chegar lá.

- **Render**: tem um recurso chamado "Secret Files" (na aba Environment
  do serviço). Você cola o conteúdo de cada `.json` lá, dá um nome de
  caminho (ex.: `service-account.json`), e o Render cria o arquivo no
  servidor sozinho, sem passar pelo Git. Depois é só apontar
  `GOOGLE_SERVICE_ACCOUNT_FILE` e `GOOGLE_DRIVE_TOKEN_FILE` (nas
  variáveis de ambiente normais) para o caminho que o Render usa para
  esses secret files (geralmente `/etc/secrets/<nome-do-arquivo>`).
- **PythonAnywhere**: mais simples ainda — a aba "Files" do painel deixa
  você fazer upload de arquivos direto para a sua pasta pessoal no
  servidor, sem Git nenhum envolvido. Sobe os dois `.json` numa pasta
  privada (fora de qualquer pasta pública do site) e aponta as variáveis
  de ambiente para esse caminho.

Quando tiver escolhido a plataforma, é só avisar que dá para preparar o
arquivo de configuração específico dela (`Procfile`, `render.yaml` etc.)
e o passo a passo exato de onde colar cada credencial.

## 7. Acessos: código da equipe, organização e administração (v3)

A organização pediu acesso fácil — a equipe muda no dia, se alguém falta
— então ninguém da equipe precisa de cadastro. Mesmo assim, a v3 fecha a
porta para quem só recebeu o link por acaso:

| Quem | Como entra | O que pode |
|---|---|---|
| Equipe (atendimento e instrutores) | **Código da equipe**, digitado uma vez por celular (vale 7 dias) | Lançar notas e posições; na Aquisição, registrar compras (com login Google) |
| Organização | **Login Google** com o e-mail de `EMAIL_ORGANIZACAO` (sem código) | Tudo da equipe, mais corrigir notas e registrar desempates |
| Administração | **Login Google** com o e-mail de `EMAIL_ADMINISTRACAO` (sem código) | Tudo da organização, mais a área de Administração |
| Qualquer pessoa | — | Ver Resultados |

- **Código da equipe** (`CODIGO_EQUIPE`): use só números (4 a 6). Troque a
  cada evento no painel do Render; quando ele muda, todos os celulares
  precisam digitar o novo. Para alguém novo no dia, basta passar o código.
  Depois de 5 tentativas erradas, o celular espera 10 minutos.
- **Organização e administração**: os e-mails ficam só nas variáveis do
  Render (nunca no código). Mais de um e-mail: separe por vírgula. O
  organizador entra pela tela do código, no link "É da organização?
  Entre com a sua Conta Google". O login só aceita contas com o e-mail
  confirmado pelo Google.
- **Aquisição**: exige o login Google (o nome e o e-mail vão para as
  colunas `responsavel_nome` e `responsavel_email`) **e** o código da
  equipe. Quem tenta acessar `/aquisicao` sem estar logado vai para o
  login e volta sozinho depois.
- `ALLOWED_EMAILS` continua opcional: se preenchida, só esses e-mails (e
  os da organização e administração) conseguem entrar com o Google.
- "Sair" encerra o login Google, mas mantém o código da equipe naquele
  celular.

## 8. A planilha mestra

Uma planilha só, com uma aba por finalidade. Nomes configurados em
`config.py` (`NOME_ABA_AQUISICAO` e o campo `sheet_name` de cada
atividade) — **precisam bater exatamente** com o nome da aba na sua
planilha (maiúsculas/acentos importam):

**Proteção contra fórmula acidental (ou maliciosa)**: qualquer texto
digitado por quem preenche o formulário (nome, telefone, clã) passa por
`sanitize_cell()` antes de ir para a planilha — se começar com `=`, `+`,
`-` ou `@`, ganha um apóstrofo na frente, forçando o Google Sheets a
tratar como texto puro em vez de tentar interpretar como fórmula. Sem
isso, um nome digitado como `=1+1` viraria uma fórmula executada de
verdade na célula.

| Aba | Tipo | Colunas (cabeçalho exato) | Quem preenche |
|---|---|---|---|
| `aquisicao` | Compras e trocas | ver "Colunas da aba `aquisicao`", abaixo | Aquisição, uma linha por atividade (ou por competidor, nas competições); Administração, nas trocas |
| `arco_flecha` | Torneio com pontuação | `nome`, `cla`, `telefone`, `tiro1` a `tiro4`, `total`, `foto_alvo`, `id_inscricao`, `situacao`, `desempate`, `alterado_por`, `alterado_em` | Aquisição copia nome/clã/telefone/código; Competições grava notas, total e o link da foto do alvo; a organização grava desempate e correções |
| `machado` | Torneio com pontuação | `nome`, `cla`, `telefone`, `tiro1` a `tiro3`, `total`, `foto_alvo`, `id_inscricao`, `situacao`, `desempate`, `alterado_por`, `alterado_em` | Idem |
| `swordplay` | Torneio por posição | `nome`, `cla`, `telefone`, `posicao`, `id_inscricao`, `situacao` | Aquisição copia nome/clã/telefone/código; Competições grava a posição |
| `rachar_lenha` | Torneio por posição (só Competição, sem Treino) | `nome`, `cla`, `telefone`, `posicao`, `id_inscricao`, `situacao` | Idem |
| `vestimenta`, `bardos`, `feiticos` | Cultural (voto popular) | `nome`, `telefone`, `posicao`, `id_inscricao`, `situacao` | Aquisição copia nome/telefone/código (sem clã); Competições grava a posição decidida pelo público |
| `beberrao` | Cultural (vence quem beber mais rápido) | `nome`, `telefone`, `posicao`, `id_inscricao`, `situacao` | Idem |
| `resumo` | Totais do evento (v3) | criada e refeita pelo próprio app | O app, com fórmulas prontas (seção 10.2) |

**Colunas de controle (v3)**, sempre no fim das abas das atividades:

- `id_inscricao`: código de cada inscrito — o código da compra mais um
  número (`ab12cd34-1`). É o mesmo na aba `aquisicao` e na aba da
  atividade, e é por ele que o app acha a pessoa certa ao gravar uma nota
  ou posição, mesmo que a planilha tenha sido reordenada ou tenha linhas
  apagadas depois que a tela foi aberta.
- `situacao`: vazio = inscrição valendo; `trocou` = a pessoa trocou de
  atividade pela Administração e sai das listas e dos resultados (a linha
  não é apagada, para ficar o histórico).
- Linhas incluídas à mão na planilha (Plano B), sem `id_inscricao`,
  continuam funcionando: nesse caso, o app só grava se o nome naquela
  linha ainda for o mesmo que a tela mostrava.

⚠️ **Nunca insira colunas no meio das abas.** O app lê e grava cada
coluna pela posição dela, e reescreve a linha 1 se o cabeçalho estiver
diferente do esperado. Uma coluna nova no meio faz notas e posições
irem para o lugar errado. Colunas extras, só depois da última.

Todas essas abas são lidas pela tela de Resultados, que mostra o Top 3 de
cada uma (por `total` nas de pontuação, por `posicao` nas demais).

O cabeçalho de qualquer uma dessas abas é criado sozinho na primeira vez
que o app precisa ler ou escrever nela — não precisa criar manualmente.
Só a aba em si precisa existir, com o nome exato (a aba `resumo` nem
isso: o app cria). Como o app confere o
cabeçalho uma vez só por processo, se você mudar uma aba com o app no ar
(renomear, recriar), reinicie o serviço no Render.

**Entre eventos, limpe as linhas de dados** (mantendo o cabeçalho) de
todas as abas: linhas antigas de outro formato podem ficar desalinhadas
com o cabeçalho atual.

### Colunas da aba `aquisicao`

`id_compra | data_hora | atividade | modo | quantidade | valor_unitario | valor_total | forma_pagamento | nome_competidor | telefone_competidor | cla_competidor | link_foto | responsavel_nome | responsavel_email | id_inscricao | situacao | observacao | assinatura`

As quatro últimas entraram na v3, no fim, para as colunas antigas (e as
fórmulas que usam as letras delas) não mudarem de lugar.

- **data_hora**: no horário de Brasília (v3). Até a v2, saía no horário
  do servidor do Render (UTC), 3 horas adiantado.
- **id_compra**: mesmo ID para todas as atividades da mesma transação —
  dá para somar por atividade ou por compra completa. São 8 caracteres
  sorteados entre 0-9 e a-f, então às vezes saem só números (normal). É
  criado pelo celular antes do envio (é o que impede compra duplicada em
  nova tentativa) e gravado sempre como texto, para o Google Sheets não
  "traduzir" IDs como `12e45678` em notação científica.
- **valor_unitario / valor_total**: vêm dos preços em `config.py`
  (`preco_unitario` — dicionário `{"Treino": valor, "Competição": valor}`
  para as atividades com os dois modos, ou um número único para as demais).
  Desde a v3 são gravados como **números** (a coluna é formatada como
  moeda pelo próprio app), e não mais como o texto "R$ 20,00" — assim as
  somas funcionam em qualquer configuração de idioma da planilha. Se faltar
  um preço, deixe `None` no lugar — a linha fica só com essas colunas vazias.
- **forma_pagamento**: PIX ou Dinheiro, uma vez por compra. **A foto é
  sempre opcional**, em qualquer forma de pagamento — o gestor preferiu
  assim para não formar fila esperando a foto. Em Dinheiro, a etapa da
  foto nem aparece na tela (não existe comprovante de transferência ali).
  Se o Drive falhar no envio por qualquer motivo, a compra é salva
  normalmente mesmo assim (a foto é opcional) — `link_foto` recebe o
  texto `"Imagem não recebida"` em vez do link. Isso fica só registrado
  na planilha, sem nenhum aviso na tela para quem está atendendo (achamos
  que só confundiria, sem ação nenhuma que desse para fazer ali na hora).
- **nome_competidor / telefone_competidor / cla_competidor**: preenchidos
  para todas as competições (as 4 físicas, só em modo Competição; as 4
  culturais, sempre). Nome e telefone (com DDD) são obrigatórios em
  todas. **Clã só existe nas 4 físicas** (Arco, Machado, Swordplay,
  Rachar Lenha) e lá é opcional — as culturais (Vestimenta, Bardos,
  Feitiços, Beberrão) não coletam clã nenhum, nem nesta aba nem nas abas
  próprias delas. Cada competidor vira sua própria linha, com
  `quantidade` sempre 1 — mesmo que várias pessoas comprem juntas,
  evitando contar errado ao somar a coluna.
- **id_inscricao**: o código de cada competidor (ver "Colunas de
  controle", acima). Vazio nas linhas de treino.
- **situacao / observacao**: vazias numa compra normal; `troca` e a
  explicação da troca nas linhas registradas pela Administração.
- **assinatura**: um resumo curto do conteúdo da compra, usado para
  reconhecer uma nova tentativa da mesma compra (seção 9).
- **Treino e Competição da mesma atividade na mesma compra**: são seções
  independentes na tela — dá para marcar as duas ao mesmo tempo.
- **Homônimos**: em todas as telas de Competições (torneios e culturais),
  se dois inscritos tiverem o mesmo nome, o telefone aparece
  automaticamente embaixo do nome dos dois, só nesse caso — para dar para
  diferenciar quem é quem. Sem homônimos, o telefone não aparece ali.

### Alimentação automática das abas de atividade

Toda compra em modo Competição também copia nome/telefone (e clã, nas
físicas) para a aba da atividade correspondente — para já chegar pronta para o
instrutor usar, sem copiar nada manualmente. Cada atividade usa o
cabeçalho certo para ela (`sheet_headers_for()` em `config.py` decide:
físicas com pontuação ganham colunas de tiro/total; físicas sem
pontuação — Swordplay, Rachar Lenha, e qualquer outra do mesmo molde que
vier depois — ganham coluna de posição; culturais ficam com
nome/telefone/posição, sem clã) — é a mesma
função usada tanto para alimentar quanto para ler depois, então não tem
risco de uma tela esperar um formato de coluna diferente do que a outra
gravou. Se a aba não existir, a compra continua sendo salva normalmente
— a cópia para a aba da atividade simplesmente não acontece, sem travar o
envio nem avisar quem está atendendo.

**Conferência automática (v3)**: a cópia roda em segundo plano, depois da
compra, e pode se perder (um reinício ou deploy do Render bem naquela
hora, uma falha do Google). Por isso, toda vez que um instrutor abre ou
atualiza a lista de uma atividade, o app compara a aba `aquisicao` com a
aba da atividade e inclui na hora quem tiver faltado. Na prática: se um
participante chegar ao instrutor e não estiver na lista, basta atualizar
a página. Ninguém é incluído duas vezes (a comparação é pelo
`id_inscricao`).

## 9. Aquisição — detalhes da tela

- **Valor total da compra**: aparece em destaque, logo antes da foto (ou
  do botão Enviar, quando a foto não aparece), recalculado a cada
  atividade/quantidade marcada — serve para conferir com o cliente antes
  de enviar.
- **Fotos comprimidas no próprio celular (v2)**: `static/fotos.js`
  redimensiona para no máximo 1280px no lado maior e salva em JPEG,
  mirando ~0,4MB (o comprovante continua legível e os furos do alvo,
  nítidos). A compressão começa assim que a foto é tirada, então no
  Enviar ela já está pronta; e no servidor a foto sobe para o Drive ao
  mesmo tempo em que a planilha é conferida. O botão mostra a etapa
  ("Preparando foto..." e depois "Enviando..."), o que também ajuda a
  saber onde está a demora, se houver. Na v1 a foto saía do celular com 5 a
  8MB e só o servidor comprimia, o que deixava tudo lento com várias
  pessoas enviando juntas. O servidor ainda comprime como reserva, caso a
  foto chegue grande (`MAX_PHOTO_DIMENSION`, `TARGET_PHOTO_BYTES`,
  `MIN_JPEG_QUALITY` em `app.py`).
- **Rascunho que sobrevive à câmera (v2)**: em celulares com pouca
  memória, o Android pode fechar o navegador enquanto a câmera está
  aberta, e a página voltava vazia (a "tela branca" que um atendente
  enfrentou no evento). Agora o que foi preenchido fica guardado no
  próprio aparelho por até 30 minutos e é restaurado sozinho, com um
  aviso; só a foto precisa ser tirada de novo.
- **Menos idas ao Google a cada envio (v2)**: cada aba da planilha é
  localizada uma vez só por processo (antes era a cada envio), a compra
  sem foto confere o código só uma vez, e a cópia dos competidores para as
  abas das atividades roda em segundo plano, depois da resposta. Uma
  compra sem foto com duas atividades caiu de 9 para 2 chamadas até o
  "Compra registrada!"; uma nota com foto, de 5 para 3 (as fotos dos
  alvos não precisam mais ser liberadas uma por uma).
- **Sem compra duplicada em nova tentativa (v2)**: o código da compra
  (`id_compra`) é criado pelo celular antes de enviar e reaproveitado se o
  atendente tentar de novo. No evento da v1, uma compra foi gravada duas
  vezes com códigos diferentes: a primeira chegou à planilha, mas a
  resposta não voltou a tempo (rede lenta) e o envio foi repetido. Agora,
  se o código já está na planilha, o servidor não grava de novo e só
  confirma a compra. O código novo só é gerado ao tocar em "Registrar nova
  compra".
- **Comprovantes privados (v2)**: na v1 cada comprovante era aberto para
  qualquer pessoa com o link. Agora ficam privados na pasta de
  `GOOGLE_DRIVE_FOLDER_ID` (ver seção 4).
- **Quantidade**: escolhida com botões "−"/"+", sem limite máximo.
- **Preço conferido no envio (v3)**: o celular manda junto o total que
  mostrou na tela, e o servidor confere com os preços atuais do
  `config.py`. Se um preço mudar no meio do evento (como aconteceu com
  Beberrão e Rachar Lenha), quem estava com a tela aberta recebe o aviso
  "Os preços foram atualizados", com um botão para atualizar a página — o
  que foi preenchido volta sozinho, já com o total certo.
- **Mesmo código, outra compra (v3)**: se um envio dá erro mas a compra
  tinha chegado, e o atendente altera a tela e reenvia, o app não diz mais
  "já registrada" (o que fazia a alteração se perder em silêncio): avisa
  que aquele código já foi usado com outros dados. Se for outro cliente, o
  botão "Registrar como nova compra" gera um código novo mantendo o que foi
  preenchido; se o cliente mudou a compra anterior, quem resolve é a
  Administração, com uma troca.
- **Prazo para gravar (v3)**: o celular desiste de esperar em 60
  segundos. Para não gravar uma compra que o atendente já acha que falhou
  (e que ele reenviaria), o servidor nunca começa a gravar depois de 35
  segundos: nesse caso responde que nada foi salvo e pede para enviar de
  novo. Com foto, ela tem até 25 segundos; depois disso a compra é salva
  com "Imagem não recebida".

## 10. Competições e Resultados

A tela de Competições é organizada como a de Resultados, em **Torneios**
e **Atividades Culturais**, e pede o código da equipe (seção 7).

- **Arco e Flecha / Arremesso de Machado** (`/competicoes/<atividade>`):
  lista os inscritos daquela aba, em ordem alfabética. Quem ainda não
  pontuou aparece clicável — toque no nome para abrir os quadrados de
  pontuação (4 tentativas no Arco, 3 no Machado — **números inteiros de 0
  a 10**, limite definido em `nota_maxima` no `config.py`); o total soma
  sozinho conforme digita.
  **Foto final do alvo**: é obrigatória, porque é a prova usada pelo
  organizador em caso de desempate. A foto vai para a pasta de
  `GOOGLE_DRIVE_ALVOS_FOLDER_ID` e o link fica na coluna `foto_alvo`. **Se
  a foto não chegar ao Drive, a nota não é salva.** Um arquivo que não
  seja foto é recusado. Depois de enviado, o nome fica cinza, com o total
  à direita. Reenviar a mesma nota (porque a resposta se perdeu) não dá
  erro; uma nota diferente para quem já foi pontuado é recusada.
  **Rascunho das notas**: as notas digitadas sobrevivem se o navegador
  recarregar ao abrir a câmera. Desde a v3, o rascunho guarda o nome da
  pessoa e vale por 2 horas: só volta se ela ainda estiver na lista e sem
  nota.
- **Correção de nota (organização)**: para quem entrou com o e-mail da
  organização ou da administração, cada nota já lançada ganha o botão
  **Corrigir**: dá para trocar as notas (a foto continua a mesma) ou
  **Limpar nota** (apaga notas e foto, e a pessoa volta para a lista do
  instrutor lançar de novo; pede um segundo toque para confirmar). A
  planilha registra quem corrigiu e quando (`alterado_por`,
  `alterado_em`). Para o resto da equipe, a nota continua travada.
- **Empates e desempate (Arco e Machado)**: quem tem o mesmo total fica
  com a mesma colocação (por exemplo 1º, 2º, 3º, 3º). O desempate só
  importa para o pódio, e só no fim da competição, por isso fica em
  **Resultados**: para quem entrou como organização ou administração,
  quando um empate vale pódio aparece, abaixo do Top 3, a seção
  **Desempate**, com a foto do alvo de cada empatado (toque para ampliar)
  e um campo de ordem (1 = quem fica na frente). A ordem vai para a coluna
  `desempate`, e o pódio passa a mostrar a ordem final. Dá para refazer:
  a seção continua aparecendo, com todos do empate (mesmo quem ficou em 4º
  depois do desempate). Se a nota de alguém do empate for corrigida, o
  desempate dela é apagado (precisa ser decidido de novo). Para o público
  e a equipe, Resultados não mostra essa seção.
- **Swordplay, Rachar Lenha e as culturais** (`/competicoes/<atividade>`):
  lista alfabética com um campo de posição por pessoa e **um único botão
  Enviar** no rodapé. Desde a v3:
  - o envio leva **só as posições que mudaram** desde que a tela foi
    aberta (o campo alterado fica destacado) — assim um celular com a
    página antiga não desfaz o que outro instrutor salvou;
  - **dá para trocar posições entre pessoas** (o 1º vira 2º e o 2º vira
    1º) ou reordenar várias de uma vez: a conferência de posição repetida
    olha o resultado final do envio;
  - **campo apagado apaga a posição** daquela pessoa;
  - se o resultado final tiver posição repetida, **nada é salvo** e a tela
    diz quem ficaria com a mesma posição;
  - tudo é gravado numa chamada só ao Google.
  O acompanhamento de quem enfrenta quem (Swordplay) ou de cada tentativa
  (Rachar Lenha) é feito no papel, e nas culturais quem decide continua
  sendo o público — a regra de cada cultural aparece no topo da tela
  (`regra_resultado` em `config.py`). O app só registra o resultado final.
- **Resultados** (`/resultados`, aberto): o Top 3 de cada atividade.
  - Arco e Machado: por total, com os empates marcados ("empate —
    aguardando desempate"); depois do desempate, a ordem final ("decidido
    no desempate"). Com empate no 3º lugar, aparecem todos os empatados.
    Cada colocado tem o botão **"Ver foto do alvo"**, que abre a foto ali
    mesmo, sem login Google.
  - Demais atividades: sempre as posições 1, 2 e 3, com **"A definir"** no
    que ainda não foi lançado (antes, se só a posição 3 estivesse lançada,
    a pessoa aparecia como "1º").
  - O telefone aparece junto ao nome — os apresentadores usam para chamar
    e contatar quem ganhou.
  - Para poupar a cota do Google (que é de 60 leituras por minuto para o
    app inteiro), cada Top 3 fica guardado por 30 segundos: uma nota nova
    pode levar até meio minuto para aparecer.

## 10.1. Tratamento de erros (v2)

O endereço do Render (`https://SEU-SERVICO.onrender.com`) é o endereço
definitivo do app. O que antes estava planejado "para depois do domínio
definitivo" foi feito na v2:

- **Falhas passageiras do Google são tentadas de novo sozinhas**
  (`tentar_google()` em `app.py`): limite de uso por minuto, instabilidade
  ou conexão lenta ganham até 3 tentativas, com 1s e 2s de espera (2s e 4s
  quando o limite por minuto estourou). **Correção da v3**: até a v2, por
  um detalhe na leitura do código do erro, as falhas da *planilha* nunca
  eram reconhecidas e não eram tentadas de novo (só as do Drive e as de
  conexão); agora são.
  Gravações que acrescentam linhas (a compra na aba `aquisicao` e a cópia
  para as abas das atividades) só são repetidas quando o Google recusou
  explicitamente — numa conexão cortada, a linha pode já ter sido gravada,
  e repetir criaria linha duplicada.
- **Mensagens claras para a equipe** (`mensagem_amigavel()`): em vez de
  textos técnicos do Google, a tela diz o que aconteceu e o que fazer
  (esperar alguns segundos, tentar de novo, avisar a organização). Os
  detalhes técnicos vão para os Logs do Render. Erros de configuração
  (aba com nome errado, credencial ausente) continuam mostrando a
  explicação completa, porque ela diz exatamente o que corrigir.
- **Envio pelo celular com tratamento próprio** (`static/rede.js`): sem
  internet, envio que passa de 60 segundos, sessão de login expirada e
  servidor reiniciando têm cada um sua mensagem. O botão nunca fica preso
  em "Enviando...". Em qualquer erro, nada do que foi preenchido se perde,
  e reenviar é seguro: a compra não duplica e a nota não é gravada duas
  vezes.
- **Sessão expirada na Aquisição**: o preenchido fica salvo no celular;
  basta atualizar a página, entrar de novo e a compra volta preenchida.
- **Erro inesperado no servidor**: nas telas, aparece a página amigável de
  erro; nos envios, uma mensagem em JSON que a tela consegue mostrar.

## 10.2. Administração (v3)

Área só para os e-mails de `EMAIL_ADMINISTRACAO`. O cartão
**Administração** aparece na tela inicial apenas para quem entrou com um
desses e-mails.

- **Trocar atividade**: para quem desiste de uma atividade e escolhe
  outra, em treino ou em competição. A compra original não é alterada (no
  treino nem dá para saber qual foi): a troca entra como um registro
  próprio na aba `aquisicao`, com um código novo:
  - saída: a atividade antiga, quantidade −1, valor −preço antigo, forma
    de pagamento "Troca";
  - entrada: a atividade nova, quantidade +1, valor +preço antigo, forma
    "Troca";
  - diferença (só se a nova for mais cara): quantidade 0, valor da
    diferença, na forma de pagamento usada para completar. Se for PIX, dá
    para tirar a foto do comprovante (opcional, como na Aquisição); ela vai
    para a pasta dos comprovantes e o link fica em `link_foto`.
  Assim o caixa (PIX e Dinheiro) só aumenta pelo que entrou de verdade,
  as linhas "Troca" se anulam, e a quantidade e a receita de cada
  atividade ficam certas. Se a nova for mais barata, o valor pago passa
  inteiro para ela, sem devolução. Na competição, a pessoa é escolhida na
  lista de inscritos; ela sai da lista da atividade antiga (marcada como
  `trocou`) e entra na da nova. **Quem já tem nota ou posição não pode
  trocar.** No treino, o app confere se ainda existe compra daquela
  atividade e modo para trocar (as compras menos as trocas já feitas); se
  não existir, recusa. Tocar em "Registrar" duas vezes não registra duas
  trocas.
- **Resumo do evento**: os totais aparecem em dois lugares, com os mesmos
  números, já considerando as trocas:
  - no app, na Administração, no botão **Ver resumo do evento** (logo
    abaixo de Trocar atividade, abre e fecha na própria tela): total do evento, PIX, Dinheiro,
    número de compras e de trocas, e quantidade e valor de cada
    atividade. É calculado na hora a partir da aba `aquisicao` (com até 30
    segundos de atraso; o link "atualizar agora" busca o mais recente);
  - na planilha, na aba `resumo`, com fórmulas. As fórmulas são do app: a
    aba é criada e refeita (em segundo plano) sempre que a Administração
    abre, e uma vez depois da primeira compra de cada processo. Se for apagada, volta sozinha. As funções vão
  com o nome em inglês (a planilha mostra traduzido: `SOMASES`) e com o
  separador do idioma da planilha (ponto e vírgula em português); o app
  confere se o Google entendeu a fórmula e, se não, troca o separador.
- **Preparar para arquivo**: depois do evento, antes de fazer a cópia de
  arquivo, deixa só o DDD nos telefones de todas as abas (o DDD serve
  para as estatísticas de público). Pede para digitar ARQUIVAR, e não dá
  para desfazer pelo app. Roteiro sugerido: Preparar para arquivo →
  Arquivo → Fazer uma cópia da planilha → limpar as linhas de dados da
  planilha original, mantendo os cabeçalhos. A cópia nasce sem o
  histórico de versões, então não guarda os telefones completos; a
  planilha original guarda no histórico de versões dela.
- **Correção de notas e desempates** não ficam aqui: a correção fica nas
  telas do Arco e do Machado, em Competições, e o desempate fica em
  Resultados (seção 10).

## 10.3. Testes automáticos (v3)

A pasta `tests/` tem testes que conferem as regras do app (código da
equipe, nota máxima, posições, empates, trocas, compra duplicada etc.)
usando uma planilha e um Drive **simulados** — não falam com o Google e
não precisam de credencial nenhuma. Para rodar no seu computador:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

No GitHub, o arquivo `.github/workflows/testes.yml` roda esses testes
sozinho a cada `push`; o resultado aparece na aba **Actions** do
repositório (✓ verde ou ✗ vermelho).

## 11. Próximos passos possíveis (não implementados ainda)

- Cancelar uma compra sem troca (por enquanto, desistência sem troca não
  é registrada: como não há devolução, a compra continua valendo).
- Reincluir "Desafio de caça ao tesouro" quando for confirmado — basta
  descomentar o bloco em `config.py`.


## Histórico de versões

### Versão 3

Preparada para o próximo evento, a partir de uma revisão completa da v2:

- **Acessos**: código da equipe em Competições e Aquisição; organização e
  administração pelo e-mail Google (seção 7).
- **Nota máxima de 10** por tentativa no Arco e no Machado.
- **Correção de nota** pela organização (corrigir ou limpar), com
  registro de quem corrigiu e quando.
- **Empates** no Top 3 do Arco e do Machado, com desempate registrado
  pela organização em Resultados, olhando as fotos dos alvos; nas demais
  atividades, "A definir" no pódio.
- **Posições**: trocar e reordenar de uma vez, apagar posição, enviar só o
  que mudou e gravar tudo numa chamada só.
- **Pessoa certa**: notas e posições são gravadas pelo código de
  inscrição (`id_inscricao`), mesmo com a planilha reordenada.
- **Conferência automática** das listas dos instrutores.
- **Administração**: troca de atividade (treino e competição), aba
  `resumo` com fórmulas prontas e preparo da planilha para arquivo (só o
  DDD).
- **Resumo do evento no app**, na Administração.
- **Velocidade**: a lista do instrutor faz as duas leituras ao mesmo
  tempo, a compra com foto faz uma conferência a menos, a autorização do
  Drive é renovada uma vez só por processo e a Administração abre sem
  esperar a aba resumo.
- **Compra**: horário de Brasília, preço conferido no envio, aviso de
  código reaproveitado com outros dados, prazo para gravar e valores
  gravados como números.
- **Correções**: novas tentativas automáticas para erros da planilha (não
  funcionavam desde a v2), limite de 16 MB por envio, fotos conferidas
  (arquivo que não é imagem é recusado), Top 3 guardado por 30 segundos
  para poupar a cota do Google.
- **Manutenção**: `pillow-heif` com versão fixa no `requirements.txt`,
  testes automáticos, ícone "maskable" ligado no `manifest.json`, service
  worker na raiz do site e mapa do sistema atualizado.

### Versão 2

Revisão feita depois do uso real da versão 1 no evento. As mudanças vieram
do que a equipe viveu no dia:

- **Culturais passam a ser lançadas no app**: entram na tela de
  Competições (agora dividida em Torneios e Atividades Culturais),
  recebem posição como Swordplay e Rachar Lenha, e em Resultados mostram
  o Top 3. O público continua decidindo; o app registra quem ganhou.
- **Foto final do alvo obrigatória** no Arco e Flecha e no Arremesso de
  Machado, usada pelo organizador para desempate, com botão "Ver foto do
  alvo" em Resultados.
- **Mais velocidade com várias pessoas enviando ao mesmo tempo**: foto
  comprimida no próprio celular, cabeçalho de cada aba conferido uma vez
  só (em vez de a cada envio) e gunicorn com threads.
- **Sem compra duplicada**: uma nova tentativa de envio da mesma compra
  (depois de erro de conexão) não gera mais um segundo registro.
- **Tratamento de erros**: novas tentativas automáticas em falhas
  passageiras do Google, mensagens claras para a equipe e envio pelo
  celular que reconhece falta de internet, sessão expirada e servidor
  reiniciando (seção 10.1).
- **Proteção contra a "tela branca"**: o formulário da Aquisição e as
  notas do Arco/Machado são restaurados se o navegador recarregar ao
  voltar da câmera.
- **Privacidade**: comprovantes de PIX deixam de ficar abertos para
  qualquer pessoa com o link, e as fotos dos alvos ganham uma pasta
  própria. As duas pastas ficam privadas: em Resultados, a foto do alvo é
  aberta pelo próprio app, sem login Google e sem link público.
- **Ajustes feitos durante o evento**: preço de Beberrão e Rachar Lenha
  passou para R$ 10,00, e o `id_compra` passou a ser gravado sempre como
  texto na planilha.

### Versão 1

Primeira versão, usada no evento: Aquisição com login Google, Competições
dos torneios físicos e Resultados com Top 3 dos torneios e lista dos
inscritos nas culturais.
