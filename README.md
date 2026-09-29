# Aço & Folha — Sistema de Gestão do Evento

**Versão 2** — revisada depois do uso real da versão 1 no evento (ver
seção "Histórico de versões", no fim deste arquivo).

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

O app tem uma tela inicial com três caminhos:

- **Aquisições** (`/aquisicao`, exige login com Google) — a equipe de
  atendimento registra cada compra: foto do comprovante (opcional),
  atividades e quantidades (com preço calculado automaticamente), forma de
  pagamento, e nome/telefone/clã de quem vai competir, quando aplicável.
  Tudo isso vira uma linha na planilha, por atividade.
- **Competições** (`/competicoes`, sem login) — organizada em Torneios e
  Atividades Culturais. Os instrutores lançam os resultados: quadrados de
  pontuação mais a foto final do alvo (obrigatória) para Arco e
  Flecha/Arremesso de Machado, e a posição final no ranking para
  Swordplay, Rachar Lenha e todas as culturais.
- **Resultados** (`/resultados`, sem login) — o Top 3 de cada torneio e de
  cada atividade cultural, calculado automaticamente a partir do que foi
  lançado em Competições.

### Mapa do sistema (PDF)

O arquivo `mapa_do_sistema.pdf`, incluído neste repositório, tem os
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
├── mapa_do_sistema.pdf         # Diagramas da estrutura do app — bom pra treinar gente nova
├── templates/
│   ├── home.html               # Tela inicial (hub dos 3 modos)
│   ├── login.html               # Login da equipe (Aquisição)
│   ├── index.html                # Formulário de Aquisição
│   ├── competicoes_hub.html      # Hub de Competições
│   ├── competicao_pontuar.html   # Lançamento de notas (Arco/Machado)
│   ├── competicao_ranking.html   # Lançamento de posição (Swordplay, Rachar Lenha, culturais)
│   ├── resultados_hub.html       # Hub de Resultados
│   ├── resultado_torneio.html    # Top 3 de um torneio
│   ├── privacidade.html          # Política de Privacidade (link p/ OAuth em produção)
│   ├── termos.html                # Termos de Serviço (idem)
│   ├── erro.html                  # Página 404/500 amigável (rede de segurança geral)
│   └── coming_soon.html          # Template genérico "em construção" (reserva)
└── static/
    ├── style.css
    ├── app.js                    # Lógica da tela de Aquisição
    ├── fotos.js                  # Compressão da foto no próprio celular (v2)
    ├── competicoes.js            # Lógica das telas de Competições
    ├── manifest.json
    ├── service-worker.js
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
GOOGLE_DRIVE_FOLDER_ID=id_da_pasta_dos_comprovantes
GOOGLE_DRIVE_ALVOS_FOLDER_ID=id_da_pasta_das_fotos_dos_alvos
GOOGLE_OAUTH_CLIENT_ID=123...apps.googleusercontent.com
GOOGLE_DRIVE_TOKEN_FILE=drive_token.json
FLASK_SECRET_KEY=uma-string-longa-e-aleatoria-qualquer
ALLOWED_EMAILS=
```

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
- **Start Command**: `gunicorn app:app --workers 2 --threads 4 --timeout 45`
  — 2 processos com 4 linhas de atendimento cada, ou seja, até 8 envios
  ao mesmo tempo. Na v1 eram 3 processos simples, e no evento, com umas 5
  pessoas enviando juntas, formava fila: como cada envio passa a maior
  parte do tempo só esperando o Google responder, as threads aproveitam
  essa espera sem gastar mais memória. O `--timeout 45` dá mais folga (padrão do gunicorn é 30s)
  antes de considerar um processo "travado" e matá-lo — importante bem
  no momento em que o serviço está acordando do modo gratuito, quando
  as chamadas ao Google costumam ficar mais lentas que o normal.
- **Tempo-limite de rede no próprio código**: `socket.setdefaulttimeout(25)`
  no topo do `app.py` garante que uma chamada ao Google (Sheets, Drive,
  verificação de login) que travar falha sozinha em 25s — dentro do
  try/except de cada rota, mostrando um erro decente — em vez de ficar
  pendurada até o gunicorn cortar o processo (que aí sim gera um 500 sem
  mensagem nenhuma pra quem está usando).
- **Manter o serviço acordado (opcional, recomendado em dia de evento)**:
  a rota `/saude` responde "ok" sem falar com o Google. Um monitor
  gratuito (como UptimeRobot ou cron-job.org) chamando
  `https://SEU-SERVICO.onrender.com/saude` a cada 10 minutos impede o
  Render de "adormecer" o serviço, e ninguém espera os 30-60 segundos do
  primeiro acesso. As 750 horas mensais do plano gratuito cobrem um
  serviço ligado o mês inteiro.
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
  login, e volta para `/aquisicao` automaticamente depois de entrar.
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

**Proteção contra fórmula acidental (ou maliciosa)**: qualquer texto
digitado por quem preenche o formulário (nome, telefone, clã) passa por
`sanitize_cell()` antes de ir para a planilha — se começar com `=`, `+`,
`-` ou `@`, ganha um apóstrofo na frente, forçando o Google Sheets a
tratar como texto puro em vez de tentar interpretar como fórmula. Sem
isso, um nome digitado como `=1+1` viraria uma fórmula executada de
verdade na célula.

| Aba | O que recebe |
|---|---|
| `aquisicao` | Uma linha por atividade comprada — ver colunas abaixo |
| `arco_flecha` | Inscritos + notas dos 4 tiros + total + link da foto do alvo |
| `machado` | Inscritos + notas dos 3 tiros + total + link da foto do alvo |
| `swordplay`, `rachar_lenha` | Inscritos + posição final no ranking |
| `vestimenta`, `bardos`, `feiticos`, `beberrao` | Inscritos (nome/telefone, sem clã) + posição final |

O cabeçalho de qualquer uma dessas abas é criado sozinho na primeira vez
que o app precisa ler ou escrever nela — não precisa criar manualmente.

### Colunas da aba `aquisicao`

`id_compra | data_hora | atividade | modo | quantidade | valor_unitario | valor_total | forma_pagamento | nome_competidor | telefone_competidor | cla_competidor | link_foto | responsavel_nome | responsavel_email`

- **id_compra**: mesmo ID para todas as atividades da mesma transação —
  dá para somar por atividade ou por compra completa.
- **valor_unitario / valor_total**: vêm dos preços em `config.py`
  (`preco_unitario` — dicionário `{"Treino": valor, "Competição": valor}`
  para as atividades com os dois modos, ou um número único para as demais),
  formatados como moeda brasileira ("R$ 20,00"). Se faltar um preço,
  deixe `None` no lugar — a linha fica só com essas colunas vazias.
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
envio nem avisar quem está atendendo (nada que desse para fazer na hora
mesmo; se acontecer, dá para perceber olhando a planilha depois).

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

## 10. Competições e Resultados

A tela de Competições é organizada como a de Resultados, em **Torneios**
e **Atividades Culturais**.

- **Arco e Flecha / Arremesso de Machado** (`/competicoes/<atividade>`):
  lista os inscritos daquela aba, em ordem alfabética, com um emoji por
  atividade para identificar rapidamente. Quem ainda não pontuou aparece
  clicável — toque no nome pra abrir os quadrados de pontuação (4 tentativas no
  Arco, 3 no Machado — **sempre números inteiros, sem casas decimais**),
  o total soma sozinho conforme digita.
  **Foto final do alvo (v2)**: é obrigatória, porque é a prova usada pelo
  organizador em caso de desempate. O botão Enviar só funciona com as
  notas e a foto; a foto vai para a pasta de `GOOGLE_DRIVE_ALVOS_FOLDER_ID`
  e o link fica na coluna `foto_alvo`. **Se a foto não chegar ao Drive, a
  nota não é salva** — as notas e a foto continuam na tela para tentar de
  novo. As notas digitadas também sobrevivem se o navegador recarregar ao
  abrir a câmera. Depois de enviado, o nome fica cinza e sem clique, com o
  clã abaixo do nome e o total à direita. A lista não atualiza sozinha —
  um link de "atualizar página" cobre novos inscritos chegando ao longo
  do dia.
- **Swordplay, Rachar Lenha e as culturais** (`/competicoes/<atividade>`):
  lista alfabética com um campo de posição por pessoa e **um único botão
  Enviar** no rodapé — manda a lista inteira de uma vez, mas só grava
  quem tem posição preenchida (não sobrescreve com vazio quem já tinha).
  **Não deixa duas pessoas ficarem com a mesma posição** — se tentar,
  essa pessoa específica fica de fora (com aviso), enquanto o resto do
  envio é salvo normalmente. O acompanhamento de quem enfrenta quem
  (Swordplay) ou de cada tentativa (Rachar Lenha) é feito no papel, e nas
  culturais quem decide continua sendo o público (voto popular em
  Vestimenta, Bardos e Feitiços; quem bebe mais rápido no Beberrão) — a
  regra de cada cultural aparece no topo da tela (`regra_resultado` em
  `config.py`). O app só registra o resultado final, o que facilita a
  premiação e os registros. Todas usam a mesma tela
  (`competicao_ranking.html`).
- **Resultados** (`/resultados`): só o Top 3 de cada atividade — por total
  no Arco/Machado, por posição nas demais (incluindo as culturais, desde
  a v2). No Arco e no Machado, cada colocado tem o botão **"Ver foto do
  alvo"**, que abre a foto ali mesmo, sem login Google (o app busca a
  imagem no Drive e guarda as mais recentes em memória, para abrir na
  hora nas vezes seguintes). O telefone do competidor
  aparece junto ao nome — os apresentadores usam pra chamar/contatar quem
  ganhou. Isso é diferente de Competições, onde o telefone fica escondido
  de propósito (só aparece em homônimos).

## 11. Próximos passos possíveis (não implementados ainda)

- Editar/cancelar uma compra ou nota enviada por engano.
- Reincluir "Desafio de caça ao tesouro" quando for confirmado — basta
  descomentar o bloco em `config.py`.
- Tratamento de erros mais robusto (planejado para depois do deploy no
  domínio definitivo).

## Histórico de versões

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
- **Proteção contra a "tela branca"**: o formulário da Aquisição e as
  notas do Arco/Machado são restaurados se o navegador recarregar ao
  voltar da câmera.
- **Privacidade**: comprovantes de PIX deixam de ficar abertos para
  qualquer pessoa com o link; as fotos dos alvos ganham uma pasta própria,
  essa sim compartilhada.
- **Ajustes feitos durante o evento**: preço de Beberrão e Rachar Lenha
  passou para R$ 10,00, e o `id_compra` passou a ser gravado sempre como
  texto na planilha.

### Versão 1

Primeira versão, usada no evento: Aquisição com login Google, Competições
dos torneios físicos e Resultados com Top 3 dos torneios e lista dos
inscritos nas culturais.
