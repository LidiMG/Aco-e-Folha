// admin.js — tela de Administração (v3): troca de atividade e preparar para arquivo.

document.addEventListener("DOMContentLoaded", () => {
  const atividades = window.ATIVIDADES_ADMIN || [];
  const errorBanner = document.getElementById("errorBanner");
  const errorList = document.getElementById("errorList");
  const successBanner = document.getElementById("successBanner");

  function mostrarErros(mensagens) {
    successBanner.hidden = true;
    errorList.innerHTML = "";
    mensagens.forEach((m) => {
      const li = document.createElement("li");
      li.textContent = m;
      errorList.appendChild(li);
    });
    errorBanner.hidden = false;
    errorBanner.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function mostrarSucesso(texto) {
    errorBanner.hidden = true;
    successBanner.textContent = texto;
    successBanner.hidden = false;
    successBanner.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function esconderAvisos() {
    errorBanner.hidden = true;
    successBanner.hidden = true;
  }

  function formatBRL(valor) {
    const [inteiro, decimal] = Math.abs(valor).toFixed(2).split(".");
    return `R$ ${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${decimal}`;
  }

  function novoId() {
    const bytes = new Uint8Array(4);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // ------------------------------------------------------------------
  // Troca de atividade
  // ------------------------------------------------------------------
  const trocaForm = document.getElementById("trocaForm");
  const saiSelect = document.getElementById("saiAtividade");
  const entraSelect = document.getElementById("entraAtividade");
  const saiPessoaCampo = document.getElementById("saiPessoaCampo");
  const saiPessoa = document.getElementById("saiPessoa");
  const saiPessoaDica = document.getElementById("saiPessoaDica");
  const entraPessoaCampo = document.getElementById("entraPessoaCampo");
  const entraNome = document.getElementById("entraNome");
  const entraTelefone = document.getElementById("entraTelefone");
  const entraCla = document.getElementById("entraCla");
  const diferencaCampo = document.getElementById("diferencaCampo");
  const diferencaTexto = document.getElementById("diferencaTexto");
  const semDevolucao = document.getElementById("semDevolucao");
  const trocaBtn = document.getElementById("trocaBtn");

  // Um código por troca, reaproveitado em nova tentativa (não duplica).
  let idTroca = novoId();
  let inscritos = [];

  function atividadeEscolhida(select) {
    return select.value === "" ? null : atividades[parseInt(select.value, 10)];
  }

  function pessoaEscolhida() {
    return saiPessoa.value === "" ? null : inscritos[parseInt(saiPessoa.value, 10)];
  }

  function atualizarTela() {
    const sai = atividadeEscolhida(saiSelect);
    const entra = atividadeEscolhida(entraSelect);

    entraPessoaCampo.hidden = !(entra && entra.competicao);
    entraCla.hidden = !(entra && entra.competicao && entra.cla);

    const precoSai = sai && sai.preco !== null ? sai.preco : 0;
    const precoEntra = entra && entra.preco !== null ? entra.preco : 0;
    const diferenca = Math.round((precoEntra - precoSai) * 100) / 100;
    diferencaCampo.hidden = !(sai && entra && diferenca > 0);
    semDevolucao.hidden = !(sai && entra && diferenca < 0);
    if (diferenca > 0) diferencaTexto.textContent = `Diferença a pagar: ${formatBRL(diferenca)}. Como foi paga?`;
  }

  async function carregarInscritos() {
    const sai = atividadeEscolhida(saiSelect);
    inscritos = [];
    saiPessoa.innerHTML = "";
    saiPessoaCampo.hidden = !(sai && sai.competicao);
    if (!sai || !sai.competicao) return;

    saiPessoaDica.textContent = "Carregando inscritos…";
    try {
      const resposta = await fetch(`/administracao/inscritos/${sai.key}`);
      const dados = await resposta.json();
      if (!dados.ok) throw new Error((dados.errors || [])[0] || "Falha ao carregar.");
      inscritos = dados.inscritos;
      const vazio = document.createElement("option");
      vazio.value = "";
      vazio.textContent = inscritos.length ? "Escolha a pessoa…" : "Ninguém inscrito nesta atividade";
      saiPessoa.appendChild(vazio);
      inscritos.forEach((p, i) => {
        const opcao = document.createElement("option");
        opcao.value = String(i);
        opcao.textContent = `${p.nome}${p.telefone ? ` (${p.telefone})` : ""}${p.tem_resultado ? " — já competiu" : ""}`;
        opcao.disabled = p.tem_resultado;
        saiPessoa.appendChild(opcao);
      });
      saiPessoaDica.textContent = "Quem já tem nota ou posição não pode trocar.";
    } catch (err) {
      saiPessoaDica.textContent = "";
      mostrarErros([err.message || "Não foi possível carregar os inscritos. Tente de novo."]);
    }
  }

  saiSelect.addEventListener("change", () => {
    esconderAvisos();
    carregarInscritos();
    atualizarTela();
  });
  entraSelect.addEventListener("change", () => {
    esconderAvisos();
    atualizarTela();
  });
  // Quem sai de uma competição normalmente é quem entra na outra: já preenche.
  saiPessoa.addEventListener("change", () => {
    const p = pessoaEscolhida();
    if (!p) return;
    entraNome.value = p.nome;
    entraTelefone.value = p.telefone;
    entraCla.value = p.cla || "";
  });

  trocaForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    esconderAvisos();
    const sai = atividadeEscolhida(saiSelect);
    const entra = atividadeEscolhida(entraSelect);
    const erros = [];
    if (!sai || !entra) erros.push("Escolha a atividade de saída e a de entrada.");
    if (sai && sai.competicao && !pessoaEscolhida()) erros.push("Escolha quem está trocando.");
    if (entra && entra.competicao && (!entraNome.value.trim() || !entraTelefone.value.trim())) {
      erros.push("Informe nome e telefone com DDD de quem entra na competição.");
    }
    const forma = document.querySelector('#formaDiferenca input:checked');
    if (!diferencaCampo.hidden && !forma) erros.push("Informe como a diferença foi paga.");
    if (erros.length) {
      mostrarErros(erros);
      return;
    }

    const pessoa = pessoaEscolhida();
    const corpo = {
      id_troca: idTroca,
      sai: Object.assign({ atividade: sai.key, modo: sai.modo }, pessoa ? { row: pessoa.row, id_inscricao: pessoa.id_inscricao, nome: pessoa.nome } : {}),
      entra: { atividade: entra.key, modo: entra.modo, nome: entraNome.value.trim(), telefone: entraTelefone.value.trim(), cla: entraCla.value.trim() },
      forma_diferenca: forma ? forma.value : null,
    };

    trocaBtn.disabled = true;
    trocaBtn.textContent = "Registrando...";
    try {
      const dados = await window.enviarAoServidor("/administracao/troca", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      if (dados.ok) {
        const avisos = dados.avisos && dados.avisos.length ? ` Atenção: ${dados.avisos.join(" ")}` : "";
        mostrarSucesso(`Troca registrada (código ${dados.id_troca}).${avisos}`);
        idTroca = novoId();
        trocaForm.reset();
        inscritos = [];
        saiPessoa.innerHTML = "";
        saiPessoaCampo.hidden = true;
        atualizarTela();
      } else {
        mostrarErros(dados.errors || ["Erro desconhecido. Tente novamente."]);
      }
    } catch (err) {
      mostrarErros([err.message || "Falha de conexão.", "Pode tocar em Registrar de novo: a troca não será duplicada."]);
    } finally {
      trocaBtn.disabled = false;
      trocaBtn.textContent = "Registrar troca";
    }
  });

  atualizarTela();

  // ------------------------------------------------------------------
  // Preparar para arquivo
  // ------------------------------------------------------------------
  const arquivoForm = document.getElementById("arquivoForm");
  const arquivoBtn = document.getElementById("arquivoBtn");
  const confirmacao = document.getElementById("arquivoConfirmacao");

  arquivoForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    esconderAvisos();
    if (confirmacao.value.trim().toUpperCase() !== "ARQUIVAR") {
      mostrarErros(["Digite ARQUIVAR no campo para confirmar."]);
      return;
    }
    arquivoBtn.disabled = true;
    arquivoBtn.textContent = "Preparando...";
    try {
      const dados = await window.enviarAoServidor("/administracao/preparar-arquivo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmacao: "ARQUIVAR" }),
      });
      if (dados.ok) {
        const total = (dados.abas || []).reduce((soma, a) => soma + a.alterados, 0);
        mostrarSucesso(`Pronto: ${total} telefone(s) ficaram só com o DDD. Agora é só fazer a cópia de arquivo da planilha.`);
        confirmacao.value = "";
      } else {
        mostrarErros(dados.errors || ["Erro desconhecido. Tente novamente."]);
      }
    } catch (err) {
      mostrarErros([err.message || "Falha de conexão.", "Pode tentar de novo: o que já virou DDD continua igual."]);
    } finally {
      arquivoBtn.disabled = false;
      arquivoBtn.textContent = "Deixar só o DDD";
    }
  });
});
