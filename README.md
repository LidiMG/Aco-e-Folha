# Aço & Folha — Sistema de Gestão do Evento

Este projeto foi desenvolvido para o evento **Aço & Folha**, para dar conta
de três frentes que antes seriam planilhas separadas e soltas: registrar as
compras de atividades no balcão, lançar os resultados dos torneios físicos
(Arco e Flecha, Arremesso de Machado, Swordplay) e acompanhar as atividades
culturais (Vestimenta, Bardos, Feitiços).

É um app web mobile (instalável como PWA), sem custo de hospedagem paga
obrigatório, e sem depender de planilhas soltas e desencontradas — tudo
alimenta a mesma planilha Google Sheets, e boa parte se alimenta sozinha.

> Este projeto foi **construído inteiramente pela Claude AI (Anthropic)**,
> a partir das orientações, decisões e testes de Lidiane Gomes — que
> conduziu cada etapa (o que construir, em que ordem, com quais regras de
> negócio), mas a escrita do código, a arquitetura técnica e a maior parte
> das soluções de UI foram trabalho do Claude.

---

## 1. O que o app faz

O app tem uma tela inicial com três caminhos:

- **Aquisições** (`/aquisicao`, exige login com Google) — a equipe de
  atendimento registra cada compra: foto do comprovante (opcional),
  atividades e quantidades (com preço calculado automaticamente), forma de
  pagamento, e nome/telefone/clã de quem vai competir, quando aplicável.
  Tudo isso vira uma linha na planilha, por atividade.
- **Competições** (`/competicoes`, sem login) — os instrutores lançam os
  resultados: quadrados de tentativa para Arco e Flecha/Arremesso de
  Machado (a nota soma sozinha), e a posição final no ranking para o
  Swordplay.
- **Resultados** (`/resultados`, sem login) — o Top 3 de cada torneio,
  calculado automaticamente a partir das notas lançadas, e a lista de
  inscritos de cada atividade cultural (que é decidida por voto popular,
  fora do app).

### Mapa do sistema (PDF)

O arquivo `mapa-do-sistema.pdf`, incluído neste repositório, tem os
diagramas da estrutura completa do app — a tela inicial e os três modos,
com o fluxo de dentro de cada um (Aquisição, Competições e Resultados).
Serve como um guia visual rápido pra quem estiver sendo treinado pra usar
o app — ajuda a entender de cara "quem faz o quê, onde" sem precisar ler
este README inteiro.

## 2. Estrutura do projeto

```
evento-app/
├── app.py                     # Flask: rotas, validação, integração Google
├── config.py                  # Atividades, preços, ícones — edite aqui para mudar o "cardápio"
├── setup_drive_auth.py        # Script de autorização única do Drive (rodar localmente)
├── requirements.txt
├── .env.example                # Modelo do .env — copie e preencha
├── mapa-do-sistema.pdf         # Diagramas da estrutura do app — bom pra treinar gente nova
├── templates/
│   ├── home.html               # Tela inicial (hub dos 3 modos)
│   ├── login.html               # Login da equipe (Aquisição)
│   ├── index.html                # Formulário de Aquisição
│   ├── competicoes_hub.html      # Hub de Competições
│   ├── competicao_pontuar.html   # Lançamento de notas (Arco/Machado)
│   ├── swordplay.html            # Lançamento de posição (Swordplay)
│   ├── resultados_hub.html       # Hub de Resultados
│   ├── resultado_torneio.html    # Top 3 de um torneio
│   ├── resultado_cultural.html   # Lista alfabética de uma atividade cultural
│   └── coming_soon.html          # Template genérico "em construção" (reserva)
└── static/
    ├── style.css
    ├── app.js                    # Lógica da tela de Aquisição
    ├── competicoes.js            # Lógica das telas de Competições
    ├── manifest.json
    ├── service-worker.js
    ├── icon-192.png / icon-512.png
    └── img/hero-aco-folha.jpg    # Imagem de topo da tela inicial
```

## 3. Configurar a conta Google (uma vez só)

Você vai testar primeiro com `lidigomes@gmail.com`, depois repete o mesmo
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
   (nunca suba esse arquivo pro GitHub).
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
   `arco_flecha`, `machado`, `swordplay`, `vestimenta`, `bardos` e
   `feiticos` (os nomes exatos ficam configurados em `config.py`), e
   compartilhe a planilha inteira com esse e-mail como **Editor**. Copie
   o ID da planilha (fica na URL, entre `/d/` e `/edit`).

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
      pedindo pra você entrar e autorizar. Ao concluir, gera um
      `drive_token.json` na mesma pasta.
   4. Pronto — o app já lê esse arquivo automaticamente daqui pra frente.
      Você só precisa repetir isso se revogar o acesso ou trocar de conta.

   As fotos vão para a raiz do seu Drive por padrão, a não ser que você
   defina `GOOGLE_DRIVE_FOLDER_ID` (veja o passo 4) apontando para uma
   pasta específica sua.

   ⚠️ **Enquanto o projeto estiver em modo "Teste"** no Google Cloud
   (padrão), essa autorização expira a cada **7 dias** — os uploads de
   foto param de funcionar até você rodar `python setup_drive_auth.py`
   de novo. Não afeta o login da equipe (isso é isento dessa regra).
   Se isso incomodar no futuro, dá pra resolver de vez publicando o
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
GOOGLE_DRIVE_FOLDER_ID=id_da_pasta_do_drive
GOOGLE_OAUTH_CLIENT_ID=123...apps.googleusercontent.com
GOOGLE_DRIVE_TOKEN_FILE=drive_token.json
FLASK_SECRET_KEY=uma-string-longa-e-aleatoria-qualquer
ALLOWED_EMAILS=
```

O app lê esse arquivo sozinho toda vez que inicia — não precisa de
`export` nenhum, em nenhum terminal, nunca mais. O `.env` já está
protegido no `.gitignore`, então não corre risco de subir pro Git por
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

- **Build Command**: `pip install -r requirements.txt && pip install pillow-heif`
  — o `pillow-heif` fica de fora do `requirements.txt` de propósito (no
  Windows local ele exige compilar C++ e trava a instalação), mas no
  Linux do Render existe pacote pronto, então é instalado só lá, à parte.
  Isso é o que permite o app comprimir fotos `.heic` (comuns em iPhone)
  também — sem esse passo extra, fotos de iPhone ainda funcionam, só não
  são comprimidas antes do upload.
- **Start Command**: `gunicorn app:app --workers 3` — 3 processos em
  paralelo, pra equipe conseguir enviar várias compras ao mesmo tempo sem
  fila. Cabe tranquilo nos 512MB de RAM do plano gratuito.
- **Plano Free**: o serviço "dorme" depois de 15 minutos sem acesso, e
  demora uns 30-60 segundos pra acordar no primeiro acesso seguinte —
  isso é normal, não é erro. Ficar dias sem uso não tem problema nenhum,
  nem risco do serviço ser apagado por inatividade.
- Alternativas equivalentes, caso o Render dê algum problema no futuro:
  **Railway** (mesma lógica de Git + variáveis de ambiente) ou
  **PythonAnywhere** (mais simples ainda, sem lidar com `gunicorn`).

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
  variáveis de ambiente normais) para o caminho que o Render usa pra
  esses secret files (geralmente `/etc/secrets/<nome-do-arquivo>`).
- **PythonAnywhere**: mais simples ainda — a aba "Files" do painel deixa
  você fazer upload de arquivos direto para a sua pasta pessoal no
  servidor, sem Git nenhum envolvido. Sobe os dois `.json` numa pasta
  privada (fora de qualquer pasta pública do site) e aponta as variáveis
  de ambiente para esse caminho.

Quando tiver escolhido a plataforma, é só avisar que dá pra preparar o
arquivo de configuração específico dela (`Procfile`, `render.yaml` etc.)
e o passo a passo exato de onde colar cada credencial.

## 7. Login da equipe

Só a Aquisição exige login — Competições e Resultados ficam abertos de
propósito, porque quem preenche muda ao longo do dia e o gestor pediu o
caminho mais simples possível.

- Quem tenta acessar `/aquisicao` sem estar logado é redirecionado pro
  login, e volta pra `/aquisicao` automaticamente depois de entrar.
- Se `ALLOWED_EMAILS` estiver definida no `.env`, só os e-mails dessa
  lista conseguem entrar. Hoje está vazia de propósito — qualquer Conta
  Google consegue logar, já que a equipe de atendimento muda no dia.
- O nome e e-mail de quem estava logado vão automaticamente para as
  colunas `responsavel_nome` e `responsavel_email` da planilha.
- "Sair" (link no topo da tela de Aquisição) encerra a sessão local.

## 8. A planilha mestra

Uma planilha só, com uma aba por finalidade. Nomes configurados em
`config.py` (`NOME_ABA_AQUISICAO` e o campo `sheet_name` de cada
atividade) — **precisam bater exatamente** com o nome da aba na sua
planilha (maiúsculas/acentos importam):

| Aba | O que recebe |
|---|---|
| `aquisicao` | Uma linha por atividade comprada — ver colunas abaixo |
| `arco_flecha` | Inscritos + notas dos 4 tiros + total |
| `machado` | Inscritos + notas dos 3 tiros + total |
| `swordplay` | Inscritos + posição final no ranking |
| `vestimenta`, `bardos`, `feiticos` | Só os inscritos (nome/clã/telefone) |

O cabeçalho de qualquer uma dessas abas é criado sozinho na primeira vez
que o app precisa ler ou escrever nela — não precisa criar manualmente.

### Colunas da aba `aquisicao`

`id_compra | data_hora | atividade | modo | quantidade | valor_unitario | valor_total | forma_pagamento | nome_competidor | telefone_competidor | cla_competidor | link_foto | responsavel_nome | responsavel_email`

- **id_compra**: mesmo ID pra todas as atividades da mesma transação —
  dá pra somar por atividade ou por compra completa.
- **valor_unitario / valor_total**: vêm dos preços em `config.py`
  (`preco_unitario` — dicionário `{"Treino": valor, "Competição": valor}`
  pras atividades com os dois modos, ou um número único pras demais),
  formatados como moeda brasileira ("R$ 20,00"). Se faltar um preço,
  deixe `None` no lugar — a linha fica só com essas colunas vazias.
- **forma_pagamento**: PIX ou Dinheiro, uma vez por compra. **A foto é
  sempre opcional**, em qualquer forma de pagamento — o gestor preferiu
  assim pra não formar fila esperando a foto. Em Dinheiro, a etapa da
  foto nem aparece na tela (não existe comprovante de transferência ali).
  Se o Drive falhar no envio por qualquer motivo, a compra é salva
  normalmente mesmo assim (a foto é opcional) — `link_foto` recebe o
  texto `"Imagem não recebida"` em vez do link. Isso fica só registrado
  na planilha, sem nenhum aviso na tela pra quem está atendendo (achamos
  que só confundiria, sem ação nenhuma que dessem pra fazer ali na hora).
- **nome_competidor / telefone_competidor / cla_competidor**: preenchidos
  pra todas as competições (as 3 físicas, só em modo Competição; as 3
  culturais, sempre). Nome e telefone (com DDD) são obrigatórios em
  todas. **Clã só existe nas 3 físicas** (Arco, Machado, Swordplay) e lá
  é opcional — as culturais (Vestimenta, Bardos, Feitiços) não coletam
  clã nenhum, nem nesta aba nem nas abas próprias delas. Cada competidor
  vira sua própria linha, com `quantidade` sempre 1 — mesmo que várias
  pessoas comprem juntas, evitando contar errado ao somar a coluna.
- **Treino e Competição da mesma atividade na mesma compra**: são seções
  independentes na tela — dá pra marcar as duas ao mesmo tempo.
- **Homônimos**: nas telas de Competições (Arco, Machado, Swordplay), se
  dois inscritos tiverem o mesmo nome, o telefone aparece automaticamente
  embaixo do nome dos dois, só nesse caso — pra dar pra diferenciar quem
  é quem. Sem homônimos, a tela continua só com nome e clã, sem poluir.
  Nas culturais isso nem é preciso, porque o telefone já aparece sempre.

### Alimentação automática das abas de atividade

Toda compra em modo Competição também copia nome/telefone (e clã, nas
físicas) pra aba da atividade correspondente — pra já chegar pronta pro
instrutor usar, sem copiar nada manualmente. Cada atividade usa o
cabeçalho certo pra ela (`sheet_headers_for()` em `config.py` decide:
físicas com pontuação ganham colunas de tiro/total, Swordplay ganha
coluna de posição, culturais ficam só com nome/telefone) — é a mesma
função usada tanto pra alimentar quanto pra ler depois, então não tem
risco de uma tela esperar um formato de coluna diferente do que a outra
gravou. Se a aba não existir, a compra continua sendo salva normalmente
— a cópia pra aba da atividade simplesmente não acontece, sem travar o
envio nem avisar quem está atendendo (nada que dessem pra fazer na hora
mesmo; se acontecer, dá pra perceber olhando a planilha depois).

## 9. Aquisição — detalhes da tela

- **Valor total da compra**: aparece em destaque, logo antes da foto (ou
  do botão Enviar, quando a foto não aparece), recalculado a cada
  atividade/quantidade marcada — serve pra conferir com o cliente antes
  de enviar.
- **Fotos comprimidas antes do upload**: redimensionadas para no máximo
  1600px no lado maior e recomprimidas em JPEG, mirando ~0,7MB por foto.
  Ajustável em `app.py` (`MAX_PHOTO_DIMENSION`, `TARGET_PHOTO_BYTES`,
  `MIN_JPEG_QUALITY`).
- **Quantidade**: escolhida com botões "−"/"+", sem limite máximo.

## 10. Competições e Resultados

- **Arco e Flecha / Arremesso de Machado** (`/competicoes/<atividade>`):
  lista os inscritos daquela aba, em ordem alfabética, com um emoji por
  atividade pra identificar rápido. Quem ainda não pontuou aparece
  clicável — toque no nome pra abrir os quadrados de tentativa (4 no
  Arco, 3 no Machado), o total soma sozinho conforme digita, e o botão
  Enviar grava só a nota daquela pessoa. Depois de enviado, o nome fica
  cinza e sem clique, com o clã abaixo do nome e o total à direita, tudo
  no mesmo tom de cinza. A lista não atualiza sozinha — um link de
  "atualizar página" cobre novos inscritos chegando ao longo do dia.
- **Swordplay** (`/competicoes/swordplay`): lista alfabética com um
  campo de posição por pessoa e **um único botão Enviar** no rodapé —
  manda a lista inteira de uma vez, mas só grava quem tem posição
  preenchida (não sobrescreve com vazio quem já tinha). O
  acompanhamento de quem enfrenta quem é feito no papel, fora do app —
  aqui só entra o resultado final, e dá pra reenviar quantas vezes
  precisar ao longo do dia.
- **Resultados** (`/resultados`): Top 3 automático de cada torneio (por
  total no Arco/Machado, por posição no Swordplay), e pra cada atividade
  cultural uma lista alfabética simples dos inscritos, sem nota — o
  resultado ali é por voto popular, fora do app. Em ambos os casos, o
  telefone do competidor aparece junto (nome/clã/telefone) — os
  apresentadores usam pra chamar/contatar quem ganhou. Isso é diferente
  de Competições, onde o telefone fica escondido de propósito (os
  instrutores não precisam dele, só poluiria a tela).

## 11. Próximos passos possíveis (não implementados ainda)

- Editar/cancelar uma compra ou nota enviada por engano.
- Reincluir "Desafio de caça ao tesouro" quando for confirmado — basta
  descomentar o bloco em `config.py`.
- Tratamento de erros mais robusto (planejado para depois do deploy no
  domínio definitivo).
