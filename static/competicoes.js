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

  document.querySelectorAll(".competitor-row .input-tiro").forEach((input) => {
    input.addEventListener("input", () => {
      const row = input.closest(".competitor-row");
      const inputs = Array.from(row.querySelectorAll(".input-tiro"));
      const total = inputs.reduce((sum, i) => sum + (parseFloat(i.value) || 0), 0);
      row.querySelector("[data-total]").textContent = total;
    });
  });

  document.querySelectorAll(".competitor-row [data-enviar]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      hideErrors();
      const row = btn.closest(".competitor-row");
      const rowNumber = parseInt(row.dataset.row, 10);
      const inputs = Array.from(row.querySelectorAll(".input-tiro"));
      const tiros = inputs.map((i) => i.value.trim());

      if (tiros.some((v) => v === "")) {
        showErrors(["Preencha todas as notas antes de enviar."]);
        return;
      }
      if (tiros.some((v) => isNaN(parseFloat(v)) || parseFloat(v) < 0)) {
        showErrors(["Cada nota precisa ser um número válido (0 ou mais)."]);
        return;
      }

      const key = window.location.pathname.split("/").filter(Boolean).pop();
      btn.disabled = true;
      btn.textContent = "Enviando...";

      try {
        const response = await fetch(`/competicoes/${key}/pontuar`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ row: rowNumber, tiros: tiros.map((v) => parseFloat(v)) }),
        });
        const data = await response.json();

        if (data.ok) {
          location.reload();
        } else {
          showErrors(data.errors || ["Erro desconhecido ao enviar. Tente novamente."]);
          btn.disabled = false;
          btn.textContent = "Enviar";
        }
      } catch (err) {
        showErrors(["Falha de conexão. Verifique a internet e tente novamente."]);
        btn.disabled = false;
        btn.textContent = "Enviar";
      }
    });
  });

  // ------------------------------------------------------------------
  // Tela do Swordplay
  // ------------------------------------------------------------------
  const swordplayForm = document.getElementById("swordplayForm");
  if (swordplayForm) {
    const submitBtn = document.getElementById("submitBtn");
    const successBanner = document.getElementById("successBanner");

    swordplayForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      hideErrors();
      if (successBanner) successBanner.hidden = true;

      const posicoes = Array.from(document.querySelectorAll(".swordplay-row")).map((row) => ({
        row: parseInt(row.dataset.row, 10),
        posicao: row.querySelector(".input-posicao").value.trim(),
      }));

      submitBtn.disabled = true;
      submitBtn.textContent = "Enviando...";

      try {
        const response = await fetch("/competicoes/swordplay", {
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
