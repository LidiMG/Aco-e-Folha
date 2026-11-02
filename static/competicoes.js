document.addEventListener("DOMContentLoaded", () => {
  const errorBanner = document.getElementById("errorBanner");
  const errorList = document.getElementById("errorList");
  const tela = document.getElementById("telaCompeticao");
  const notaMaxima = tela && tela.dataset.notaMaxima ? parseInt(tela.dataset.notaMaxima, 10) : null;

  function showErrors(messages) {
    if (!errorBanner || !errorList) return;
    errorList.innerHTML = "";
    messages.forEach((msg) => {
      const li = document.createElement("li");
      li.textContent = msg;
      errorList.appendChild(li);
    });
    errorBanner.hidden = false;
    errorBanner.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function hideErrors() {
    if (errorBanner) errorBanner.hidden = true;
  }

  // Aceita vírgula como separador decimal (padrão brasileiro) além do ponto.
  // Sem isso, parseFloat("8,5") entende só "8" e descarta o ",5" em silêncio.
  function parseScoreValue(v) {
    return parseFloat(String(v).trim().replace(",", "."));
  }

  // Identificação da pessoa enviada junto com cada nota/posição (v3): com o
  // código de inscrição, o servidor acha a pessoa certa mesmo que a planilha
  // tenha sido reordenada depois que a tela foi aberta.
  function identificacao(el) {
    return {
      row: parseInt(el.dataset.row, 10),
      id_inscricao: el.dataset.id || "",
      nome: el.dataset.nome || "",
    };
  }

  function erroDasNotas(valores) {
    if (valores.some((v) => v === "")) return "Preencha todas as notas antes de enviar.";
    const numeros = valores.map(parseScoreValue);
    if (numeros.some((n) => isNaN(n) || n < 0)) return "Cada nota precisa ser um número válido (0 ou mais).";
    if (numeros.some((n) => !Number.isInteger(n))) return "Cada nota precisa ser um número inteiro (sem casas decimais).";
    if (notaMaxima !== null && numeros.some((n) => n > notaMaxima)) return `Cada nota vai de 0 a ${notaMaxima}.`;
    return null;
  }

  function valoresDoCorpo(body) {
    return Array.from(body.querySelectorAll(".input-tiro")).map((i) => i.value.trim());
  }

  function atualizarTotal(body) {
    const total = valoresDoCorpo(body).reduce((soma, v) => soma + (parseScoreValue(v) || 0), 0);
    body.querySelector("[data-total]").textContent = total;
  }

  // ------------------------------------------------------------------
  // Tela de pontuação (Arco e Flecha / Arremesso de Machado)
  // ------------------------------------------------------------------
  document.querySelectorAll(".competitor-row [data-toggle]").forEach((toggleBtn) => {
    toggleBtn.addEventListener("click", () => {
      const body = toggleBtn.closest(".competitor-row").querySelector('[data-modo="lancar"]');
      body.hidden = !body.hidden;
    });
  });

  // --- Rascunho das notas -------------------------------------------------
  // Se o celular fechar o navegador ao abrir a câmera (foto do alvo), as
  // notas digitadas não se perdem: ficam guardadas no aparelho e voltam
  // sozinhas. v3: o rascunho guarda o nome da pessoa e vale por 2 horas —
  // só volta se ela ainda estiver na lista e sem nota (antes, um rascunho
  // antigo podia reaparecer em outra pessoa que ficasse na mesma linha).
  const CHAVE_NOTAS = `notas_rascunho:${window.location.pathname}`;
  const VALIDADE_RASCUNHO_NOTAS_MS = 2 * 60 * 60 * 1000;

  function lerRascunhoNotas() {
    try { return JSON.parse(localStorage.getItem(CHAVE_NOTAS) || "{}") || {}; } catch (err) { return {}; }
  }

  function gravarRascunhoNotas(rascunho) {
    try {
      if (Object.keys(rascunho).length === 0) localStorage.removeItem(CHAVE_NOTAS);
      else localStorage.setItem(CHAVE_NOTAS, JSON.stringify(rascunho));
    } catch (err) { /* sem armazenamento: segue sem rascunho */ }
  }

  function salvarNotasDaLinha(row) {
    const body = row.querySelector('[data-modo="lancar"]');
    if (!body) return;
    const valores = valoresDoCorpo(body);
    const rascunho = lerRascunhoNotas();
    if (valores.some((v) => v !== "")) {
      rascunho[row.dataset.chave] = { nome: row.dataset.nome, valores, salvoEm: Date.now() };
    } else {
      delete rascunho[row.dataset.chave];
    }
    gravarRascunhoNotas(rascunho);
  }

  document.querySelectorAll('[data-modo] .input-tiro').forEach((input) => {
    input.addEventListener("input", () => {
      const body = input.closest("[data-modo]");
      atualizarTotal(body);
      if (body.dataset.modo === "lancar") salvarNotasDaLinha(input.closest(".competitor-row"));
    });
  });

  (function restaurarNotas() {
    const rascunho = lerRascunhoNotas();
    let restaurou = false;
    Object.entries(rascunho).forEach(([chave, guardado]) => {
      const valido = guardado && Array.isArray(guardado.valores) && Date.now() - (guardado.salvoEm || 0) < VALIDADE_RASCUNHO_NOTAS_MS;
      const row = valido ? Array.from(document.querySelectorAll(".competitor-row")).find((r) => r.dataset.chave === chave) : null;
      const body = row && row.querySelector('[data-modo="lancar"]');
      if (!body || row.dataset.nome !== guardado.nome) {
        delete rascunho[chave]; // vencido, já pontuado ou não é mais a mesma pessoa: descarta
        return;
      }
      body.querySelectorAll(".input-tiro").forEach((input, i) => { input.value = guardado.valores[i] || ""; });
      atualizarTotal(body);
      body.hidden = false;
      restaurou = true;
    });
    gravarRascunhoNotas(rascunho);
    if (restaurou) {
      const aviso = document.createElement("div");
      aviso.className = "banner banner--info";
      aviso.textContent = "Recuperamos as notas que estavam digitadas. Tire a foto do alvo de novo antes de enviar.";
      const lista = document.querySelector(".competitor-list");
      lista.parentNode.insertBefore(aviso, lista);
    }
  })();

  // --- Foto do alvo: obrigatória, prova para desempate ----------------------
  document.querySelectorAll(".competitor-row .input-foto-alvo").forEach((input) => {
    const row = input.closest(".competitor-row");
    const preview = row.querySelector(".alvo-foto__preview");
    const textoBotao = row.querySelector(".alvo-foto__texto");

    // Salva as notas logo antes da câmera abrir (é quando o celular pode
    // fechar o navegador por falta de memória).
    input.addEventListener("click", () => salvarNotasDaLinha(row));

    input.addEventListener("change", () => {
      window.prepararFoto(input); // já começa a comprimir
      const file = input.files[0];
      if (!file) return;
      if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
      preview.dataset.url = URL.createObjectURL(file);
      preview.src = preview.dataset.url;
      preview.hidden = false;
      textoBotao.textContent = "Trocar foto do alvo";
    });
  });

  document.querySelectorAll(".competitor-row [data-enviar]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      hideErrors();
      const row = btn.closest(".competitor-row");
      const body = row.querySelector('[data-modo="lancar"]');
      const tiros = valoresDoCorpo(body);
      const fotoInput = row.querySelector(".input-foto-alvo");

      const erro = erroDasNotas(tiros);
      if (erro) {
        showErrors([erro]);
        return;
      }
      if (!fotoInput || !fotoInput.files[0]) {
        showErrors(["Tire a foto do alvo antes de enviar — ela é obrigatória (serve para desempate)."]);
        return;
      }

      btn.disabled = true;
      btn.textContent = "Preparando foto...";

      try {
        const foto = await window.fotoPronta(fotoInput);
        btn.textContent = "Enviando...";
        const id = identificacao(row);
        const formData = new FormData();
        formData.append("row", String(id.row));
        formData.append("id_inscricao", id.id_inscricao);
        formData.append("nome", id.nome);
        formData.append("tiros", JSON.stringify(tiros.map(parseScoreValue)));
        formData.append("foto_alvo", foto);

        const data = await window.enviarAoServidor(`/competicoes/${tela.dataset.key}/pontuar`, { method: "POST", body: formData });

        if (data.ok) {
          const rascunho = lerRascunhoNotas();
          delete rascunho[row.dataset.chave];
          gravarRascunhoNotas(rascunho);
          location.reload();
        } else {
          // Nada se perde: notas e foto continuam na tela para tentar de novo.
          showErrors(data.errors || ["Erro desconhecido ao enviar. Tente novamente."]);
          btn.disabled = false;
          btn.textContent = "Enviar";
        }
      } catch (err) {
        showErrors([
          err.message || "Falha de conexão.",
          "As notas e a foto continuam aqui: toque em Enviar de novo. Se a nota já tiver sido salva, o app reconhece e não grava duas vezes.",
        ]);
        btn.disabled = false;
        btn.textContent = "Enviar";
      }
    });
  });

  // --- Correção de nota (v3) — só aparece para a organização ---------------
  document.querySelectorAll(".competitor-row [data-corrigir]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const body = btn.closest(".competitor-row").querySelector('[data-modo="corrigir"]');
      body.hidden = !body.hidden;
    });
  });

  async function enviarCorrecao(row, acao, botao, textoOriginal) {
    hideErrors();
    const body = row.querySelector('[data-modo="corrigir"]');
    const corpo = Object.assign({ acao }, identificacao(row));
    if (acao === "corrigir") {
      const tiros = valoresDoCorpo(body);
      const erro = erroDasNotas(tiros);
      if (erro) {
        showErrors([erro]);
        return;
      }
      corpo.tiros = tiros.map(parseScoreValue);
    }
    botao.disabled = true;
    botao.textContent = "Salvando...";
    try {
      const data = await window.enviarAoServidor(`/competicoes/${tela.dataset.key}/corrigir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      if (data.ok) {
        location.reload();
        return;
      }
      showErrors(data.errors || ["Erro desconhecido ao salvar. Tente novamente."]);
    } catch (err) {
      showErrors([err.message || "Falha de conexão.", "Toque de novo para tentar outra vez."]);
    }
    botao.disabled = false;
    botao.textContent = textoOriginal;
  }

  document.querySelectorAll(".competitor-row [data-salvar-correcao]").forEach((btn) => {
    btn.addEventListener("click", () => enviarCorrecao(btn.closest(".competitor-row"), "corrigir", btn, "Salvar"));
  });

  // "Limpar nota" pede um segundo toque para confirmar (apaga notas e foto).
  document.querySelectorAll(".competitor-row [data-limpar]").forEach((btn) => {
    let cronometro = null;
    btn.addEventListener("click", () => {
      if (btn.dataset.confirmar !== "1") {
        btn.dataset.confirmar = "1";
        btn.textContent = "Toque de novo para limpar";
        cronometro = setTimeout(() => {
          btn.dataset.confirmar = "";
          btn.textContent = "Limpar nota";
        }, 4000);
        return;
      }
      clearTimeout(cronometro);
      btn.dataset.confirmar = "";
      enviarCorrecao(btn.closest(".competitor-row"), "limpar", btn, "Limpar nota");
    });
  });

  // ------------------------------------------------------------------
  // Tela de posição no ranking (Swordplay, Rachar Lenha e as culturais)
  // ------------------------------------------------------------------
  // v3: envia só as posições que mudaram desde que a tela foi aberta (assim
  // um celular com a página antiga não desfaz o que outro instrutor salvou),
  // e campo apagado = posição apagada.
  const rankingForm = document.getElementById("rankingForm");
  if (rankingForm) {
    const submitBtn = document.getElementById("submitBtn");
    const successBanner = document.getElementById("successBanner");
    const key = rankingForm.dataset.key;

    function mudou(row) {
      return row.querySelector(".input-posicao").value.trim() !== (row.dataset.original || "").trim();
    }

    rankingForm.querySelectorAll(".ranking-row .input-posicao").forEach((input) => {
      input.addEventListener("input", () => {
        input.classList.toggle("input-posicao--alterada", mudou(input.closest(".ranking-row")));
      });
    });

    rankingForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      hideErrors();
      if (successBanner) successBanner.hidden = true;

      const alteradas = Array.from(document.querySelectorAll(".ranking-row")).filter(mudou);
      if (alteradas.length === 0) {
        showErrors(["Nenhuma posição foi alterada desde a última vez que a página foi aberta ou salva."]);
        return;
      }
      const posicoes = alteradas.map((row) =>
        Object.assign(identificacao(row), { posicao: row.querySelector(".input-posicao").value.trim() })
      );

      submitBtn.disabled = true;
      submitBtn.textContent = "Enviando...";

      try {
        const data = await window.enviarAoServidor(`/competicoes/${key}/posicao`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ posicoes }),
        });

        if (data.ok) {
          alteradas.forEach((row) => {
            const input = row.querySelector(".input-posicao");
            row.dataset.original = input.value.trim();
            input.classList.remove("input-posicao--alterada");
          });
          if (successBanner) {
            successBanner.hidden = false;
            successBanner.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        } else {
          showErrors(data.errors || ["Erro desconhecido ao enviar. Tente novamente."]);
        }
      } catch (err) {
        showErrors([
          err.message || "Falha de conexão.",
          "As posições continuam preenchidas: toque em Enviar de novo (reenviar não duplica nada).",
        ]);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Enviar posições";
      }
    });
  }
});
