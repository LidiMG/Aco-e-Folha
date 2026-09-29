document.addEventListener("DOMContentLoaded", () => {
  const errorBanner = document.getElementById("errorBanner");
  const errorList = document.getElementById("errorList");

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

  // Aceita vírgula como separador decimal (padrão brasileiro) além do ponto.
  // Sem isso, parseFloat("8,5") entende só "8" e descarta o ",5" em silêncio,
  // sem erro nenhum — a nota gravaria errada sem ninguém perceber.
  function parseScoreValue(v) {
    return parseFloat(String(v).trim().replace(",", "."));
  }
  function hideErrors() {
    if (errorBanner) errorBanner.hidden = true;
  }

  // ------------------------------------------------------------------
  // Tela de pontuação (Arco e Flecha / Arremesso de Machado)
  // ------------------------------------------------------------------
  document.querySelectorAll(".competitor-row[data-row] [data-toggle]").forEach((toggleBtn) => {
    toggleBtn.addEventListener("click", () => {
      const body = toggleBtn.closest(".competitor-row").querySelector(".competitor-row__body");
      body.hidden = !body.hidden;
    });
  });

  // --- Rascunho das notas (v2) ------------------------------------------
  // Se o celular fechar o navegador ao abrir a câmera (foto do alvo), as
  // notas digitadas não se perdem: ficam guardadas no aparelho e voltam
  // sozinhas. Só a foto precisa ser tirada de novo.
  const CHAVE_NOTAS = `notas_rascunho:${window.location.pathname}`;

  function lerRascunhoNotas() {
    try { return JSON.parse(localStorage.getItem(CHAVE_NOTAS) || "{}"); } catch (err) { return {}; }
  }

  function gravarRascunhoNotas(rascunho) {
    try {
      if (Object.keys(rascunho).length === 0) localStorage.removeItem(CHAVE_NOTAS);
      else localStorage.setItem(CHAVE_NOTAS, JSON.stringify(rascunho));
    } catch (err) { /* sem armazenamento: segue sem rascunho */ }
  }

  function salvarNotasDaLinha(row) {
    const valores = Array.from(row.querySelectorAll(".input-tiro")).map((i) => i.value);
    const rascunho = lerRascunhoNotas();
    if (valores.some((v) => v.trim() !== "")) rascunho[row.dataset.row] = valores;
    else delete rascunho[row.dataset.row];
    gravarRascunhoNotas(rascunho);
  }

  function atualizarTotalDaLinha(row) {
    const inputs = Array.from(row.querySelectorAll(".input-tiro"));
    const total = inputs.reduce((sum, i) => sum + (parseScoreValue(i.value) || 0), 0);
    row.querySelector("[data-total]").textContent = total;
  }

  document.querySelectorAll(".competitor-row .input-tiro").forEach((input) => {
    input.addEventListener("input", () => {
      const row = input.closest(".competitor-row");
      atualizarTotalDaLinha(row);
      salvarNotasDaLinha(row);
    });
  });

  (function restaurarNotas() {
    const rascunho = lerRascunhoNotas();
    let restaurou = false;
    Object.entries(rascunho).forEach(([rowNumber, valores]) => {
      const row = document.querySelector(`.competitor-row[data-row="${rowNumber}"]`);
      const body = row && row.querySelector(".competitor-row__body");
      if (!body) {
        delete rascunho[rowNumber]; // já pontuado (ou não existe mais): descarta
        return;
      }
      row.querySelectorAll(".input-tiro").forEach((input, i) => { input.value = valores[i] || ""; });
      atualizarTotalDaLinha(row);
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

  // --- Foto do alvo (v2): obrigatória, prova para desempate ---------------
  document.querySelectorAll(".competitor-row .input-foto-alvo").forEach((input) => {
    const row = input.closest(".competitor-row");
    const preview = row.querySelector(".alvo-foto__preview");
    const textoBotao = row.querySelector(".alvo-foto__texto");

    // Salva as notas logo antes da câmera abrir (é quando o celular pode
    // fechar o navegador por falta de memória).
    input.addEventListener("click", () => salvarNotasDaLinha(row));

    input.addEventListener("change", () => {
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
      const rowNumber = parseInt(row.dataset.row, 10);
      const inputs = Array.from(row.querySelectorAll(".input-tiro"));
      const tiros = inputs.map((i) => i.value.trim());
      const fotoInput = row.querySelector(".input-foto-alvo");

      if (tiros.some((v) => v === "")) {
        showErrors(["Preencha todas as notas antes de enviar."]);
        return;
      }
      if (tiros.some((v) => isNaN(parseScoreValue(v)) || parseScoreValue(v) < 0)) {
        showErrors(["Cada nota precisa ser um número válido (0 ou mais)."]);
        return;
      }
      if (tiros.some((v) => !Number.isInteger(parseScoreValue(v)))) {
        showErrors(["Cada nota precisa ser um número inteiro (sem casas decimais)."]);
        return;
      }
      if (!fotoInput || !fotoInput.files[0]) {
        showErrors(["Tire a foto do alvo antes de enviar — ela é obrigatória (serve para desempate)."]);
        return;
      }

      const key = window.location.pathname.split("/").filter(Boolean).pop();
      btn.disabled = true;
      btn.textContent = "Enviando...";

      try {
        const foto = await window.comprimirFoto(fotoInput.files[0]);
        const formData = new FormData();
        formData.append("row", String(rowNumber));
        formData.append("tiros", JSON.stringify(tiros.map((v) => parseScoreValue(v))));
        formData.append("foto_alvo", foto);

        const response = await fetch(`/competicoes/${key}/pontuar`, { method: "POST", body: formData });
        const data = await response.json();

        if (data.ok) {
          const rascunho = lerRascunhoNotas();
          delete rascunho[String(rowNumber)];
          gravarRascunhoNotas(rascunho);
          location.reload();
        } else {
          // Nada se perde: notas e foto continuam na tela para tentar de novo.
          showErrors(data.errors || ["Erro desconhecido ao enviar. Tente novamente."]);
          btn.disabled = false;
          btn.textContent = "Enviar";
        }
      } catch (err) {
        showErrors(["Falha de conexão. As notas e a foto continuam aqui — verifique a internet e toque em Enviar de novo."]);
        btn.disabled = false;
        btn.textContent = "Enviar";
      }
    });
  });

  // ------------------------------------------------------------------
  // Tela de posição no ranking (Swordplay, Rachar Lenha e as culturais)
  // ------------------------------------------------------------------
  const rankingForm = document.getElementById("rankingForm");
  if (rankingForm) {
    const submitBtn = document.getElementById("submitBtn");
    const successBanner = document.getElementById("successBanner");
    const key = rankingForm.dataset.key;

    rankingForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      hideErrors();
      if (successBanner) successBanner.hidden = true;

      const posicoes = Array.from(document.querySelectorAll(".ranking-row")).map((row) => ({
        row: parseInt(row.dataset.row, 10),
        posicao: row.querySelector(".input-posicao").value.trim(),
      }));

      submitBtn.disabled = true;
      submitBtn.textContent = "Enviando...";

      try {
        const response = await fetch(`/competicoes/${key}/posicao`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ posicoes }),
        });
        const data = await response.json();

        if (data.ok) {
          if (successBanner) {
            successBanner.hidden = false;
            successBanner.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        } else {
          showErrors(data.errors || ["Erro desconhecido ao enviar. Tente novamente."]);
        }
      } catch (err) {
        showErrors(["Falha de conexão. Verifique a internet e tente novamente."]);
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Enviar posições";
      }
    });
  }
});
