if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/service-worker.js").catch(() => {
      // Falha silenciosa: o app funciona normalmente mesmo sem o service worker.
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("purchaseForm");
  const submitBtn = document.getElementById("submitBtn");
  const errorBanner = document.getElementById("errorBanner");
  const errorList = document.getElementById("errorList");
  const successBanner = document.getElementById("successBanner");
  const successId = document.getElementById("successId");
  const successWarnings = document.getElementById("successWarnings");
  const newSubmissionBtn = document.getElementById("newSubmissionBtn");
  const photoInput = document.getElementById("photoInput");
  const photoPreview = document.getElementById("photoPreview");
  const retakePhotoBtn = document.getElementById("retakePhotoBtn");
  const cameraTrigger = document.querySelector(".camera-trigger");
  const stepPhoto = document.getElementById("stepPhoto");
  const pagamentoGroup = document.querySelector('[data-role="pagamento"]');
  const totalValueEl = document.getElementById("totalValue");

  // --- Valor total da compra, recalculado a cada mudança -----------------
  function formatBRL(value) {
    const fixed = value.toFixed(2);
    const [intPart, decPart] = fixed.split(".");
    const comMilhar = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return `R$ ${comMilhar},${decPart}`;
  }

  function getPrecoUnitario(activityKey, modo) {
    const precos = window.ACTIVITY_PRICES || {};
    const raw = precos[activityKey];
    if (raw === undefined || raw === null) return null;
    if (typeof raw === "object") {
      const valor = raw[modo];
      return valor === undefined || valor === null ? null : valor;
    }
    return raw; // atividade de modo fixo: preço é um número único
  }

  function updateTotal() {
    let total = 0;

    document.querySelectorAll(".activity-subcard").forEach((subcard) => {
      const toggle = subcard.querySelector(".activity-toggle");
      if (!toggle.checked) return;
      const quantidade = parseInt(subcard.querySelector(".input-quantidade").value, 10) || 0;
      const preco = getPrecoUnitario(subcard.dataset.activity, subcard.dataset.modo);
      if (preco !== null) total += preco * quantidade;
    });

    document.querySelectorAll('.activity-card[data-has-mode="false"]').forEach((card) => {
      const toggle = card.querySelector(".activity-toggle");
      if (!toggle.checked) return;
      const quantidade = parseInt(card.querySelector(".input-quantidade").value, 10) || 0;
      const preco = getPrecoUnitario(card.dataset.activity, "Competição");
      if (preco !== null) total += preco * quantidade;
    });

    totalValueEl.textContent = formatBRL(total);
  }

  // --- Forma de pagamento: some com a etapa da foto quando for Dinheiro --
  // (a foto é o comprovante do PIX; em dinheiro não existe esse comprovante)
  function isDinheiroSelecionado() {
    const checked = pagamentoGroup.querySelector("input:checked");
    return !!checked && checked.value === "Dinheiro";
  }

  function updatePhotoRequirement() {
    if (isDinheiroSelecionado()) {
      stepPhoto.hidden = true;
      resetPhotoStep();
    } else {
      stepPhoto.hidden = false;
    }
  }

  pagamentoGroup.querySelectorAll("input").forEach((radio) => {
    radio.addEventListener("change", updatePhotoRequirement);
  });

  // --- Seletor de quantidade (+/-) em vez de digitar -----------------------
  function setStepperValue(stepper, newValue) {
    const clamped = Math.max(0, newValue);
    const hiddenInput = stepper.querySelector(".input-quantidade");
    const valueEl = stepper.querySelector(".qty-stepper__value");
    const minusBtn = stepper.querySelector('[data-step="-1"]');

    hiddenInput.value = clamped;
    valueEl.textContent = clamped;
    minusBtn.disabled = clamped <= 0;
    hiddenInput.dispatchEvent(new Event("input", { bubbles: true }));
    updateTotal();
  }

  function resetStepper(stepper) {
    setStepperValue(stepper, 0);
  }

  document.querySelectorAll(".qty-stepper").forEach((stepper) => {
    stepper.querySelectorAll(".qty-stepper__btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const hiddenInput = stepper.querySelector(".input-quantidade");
        const current = parseInt(hiddenInput.value, 10) || 0;
        const step = parseInt(btn.dataset.step, 10);
        setStepperValue(stepper, current + step);
      });
    });
    resetStepper(stepper); // garante estado inicial consistente (0, botão "−" desabilitado)
  });

  // --- Nomes + telefone + clã de competidores: 1 trio de campos por unidade
  // (existe tanto em sub-cards de Competição quanto em atividades de modo
  // fixo — qualquer atividade marcada como collects_competitor_names)
  function syncCompetitorNameFields(container) {
    const competitorBlock = container.querySelector('[data-role="competidores"]');
    if (!competitorBlock) return;

    const list = competitorBlock.querySelector(".competitor-names__list");
    const qtyInput = container.querySelector(".input-quantidade");
    const quantidade = parseInt(qtyInput.value, 10) || 0;

    if (quantidade <= 0) {
      competitorBlock.hidden = true;
      list.innerHTML = "";
      return;
    }

    competitorBlock.hidden = false;

    while (list.children.length < quantidade) {
      const idx = list.children.length + 1;

      const entry = document.createElement("div");
      entry.className = "competitor-entry";

      const nomeInput = document.createElement("input");
      nomeInput.type = "text";
      nomeInput.className = "input-competidor-nome";
      nomeInput.placeholder = `Nome do competidor ${idx}`;

      const telInput = document.createElement("input");
      telInput.type = "tel";
      telInput.className = "input-competidor-telefone";
      telInput.placeholder = "Telefone com DDD";
      telInput.inputMode = "tel";

      const claInput = document.createElement("input");
      claInput.type = "text";
      claInput.className = "input-competidor-cla";
      claInput.placeholder = "Clã (opcional)";

      entry.appendChild(nomeInput);
      entry.appendChild(telInput);
      entry.appendChild(claInput);
      list.appendChild(entry);
    }
    while (list.children.length > quantidade) {
      list.removeChild(list.lastElementChild);
    }
  }

  document.querySelectorAll(
    '.activity-subcard[data-collects-names="true"], .activity-card[data-has-mode="false"][data-collects-names="true"]'
  ).forEach((container) => {
    const qtyInput = container.querySelector(".input-quantidade");
    qtyInput.addEventListener("input", () => syncCompetitorNameFields(container));
  });

  // --- Toggle de cada card/sub-card de atividade --------------------------
  document.querySelectorAll(".activity-toggle").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const subcard = checkbox.closest(".activity-subcard");
      const container = subcard || checkbox.closest(".activity-card");
      const body = container.querySelector(subcard ? ".activity-subcard__body" : ".activity-card__body");
      const isChecked = checkbox.checked;

      body.hidden = !isChecked;
      container.classList.toggle(subcard ? "activity-subcard--active" : "activity-card--active", isChecked);

      if (!isChecked) {
        // Limpa os campos ao desmarcar, para não sobrar dado "fantasma"
        container.querySelectorAll(".qty-stepper").forEach((s) => resetStepper(s));
        container.querySelectorAll("input[type=radio]").forEach((r) => (r.checked = false));
        const competitorContainer = container.querySelector('[data-role="competidores"]');
        if (competitorContainer) {
          competitorContainer.hidden = true;
          competitorContainer.querySelector(".competitor-names__list").innerHTML = "";
        }
      }

      updateTotal();
    });
  });

  // --- Etapa da foto: mostrar/limpar -------------------------------------
  // A foto agora fica no final do formulário (o atendente preenche o resto
  // enquanto o cliente faz o PIX), então não trava mais o resto da tela —
  // só cuida da própria pré-visualização.
  function resetPhotoStep() {
    photoInput.value = "";
    photoPreview.src = "";
    photoPreview.hidden = true;
    cameraTrigger.hidden = false;
    retakePhotoBtn.hidden = true;
  }

  photoInput.addEventListener("change", () => {
    const file = photoInput.files[0];
    if (!file) {
      photoPreview.hidden = true;
      cameraTrigger.hidden = false;
      retakePhotoBtn.hidden = true;
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      photoPreview.src = e.target.result;
      photoPreview.hidden = false;
      cameraTrigger.hidden = true;
      retakePhotoBtn.hidden = false;
    };
    reader.readAsDataURL(file);
  });

  retakePhotoBtn.addEventListener("click", () => {
    photoInput.click();
  });

  // O celular/navegador pode restaurar a tela de uma visita anterior ao
  // voltar pro app (cache de navegação) — isso reexibe a pré-visualização
  // da última foto tirada, mas NÃO restaura o arquivo de verdade (os
  // navegadores nunca fazem isso, por segurança). Sem isso, ficava uma
  // miniatura "fantasma" na tela que o app corretamente recusava usar.
  // Forçamos a limpeza sempre que a página volta a ficar visível assim.
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      resetPhotoStep();
    }
  });

  function hideBanners() {
    errorBanner.hidden = true;
    successBanner.hidden = true;
    successWarnings.hidden = true;
    successWarnings.innerHTML = "";
  }

  function showErrors(messages) {
    errorList.innerHTML = "";
    messages.forEach((msg) => {
      const li = document.createElement("li");
      li.textContent = msg;
      errorList.appendChild(li);
    });
    errorBanner.hidden = false;
    errorBanner.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // --- Monta o payload de atividades marcadas e valida no cliente --------
  function collectCompetidores(container, quantidade, fullLabel, errors) {
    const competitorContainer = container.querySelector('[data-role="competidores"]');
    if (!competitorContainer) return undefined;

    const entries = Array.from(competitorContainer.querySelectorAll(".competitor-entry"));
    const competidores = entries.map((entry) => ({
      nome: entry.querySelector(".input-competidor-nome").value.trim(),
      telefone: entry.querySelector(".input-competidor-telefone").value.trim(),
      cla: entry.querySelector(".input-competidor-cla").value.trim(),
    }));
    const completos = competidores.filter((c) => c.nome && c.telefone);

    if (quantidade > 0 && completos.length !== quantidade) {
      errors.push(
        `Informe nome e telefone (com DDD) de cada competidor de ${fullLabel} ` +
        `(${quantidade} esperado(s), ${completos.length} completo(s)).`
      );
    }
    return completos;
  }

  function collectActivitiesAndValidate() {
    const errors = [];
    const activities = [];

    // Atividades com Treino/Competição: cada sub-card marcado vira um item —
    // é assim que treino e competição da mesma atividade convivem na mesma compra.
    document.querySelectorAll(".activity-subcard").forEach((subcard) => {
      const toggle = subcard.querySelector(".activity-toggle");
      if (!toggle.checked) return;

      const key = subcard.dataset.activity;
      const modo = subcard.dataset.modo;
      const activityLabel = subcard.closest(".activity-card").querySelector(".activity-card__title").textContent;
      const fullLabel = `${activityLabel} (${modo})`;

      const qtyInput = subcard.querySelector(".input-quantidade");
      const quantidade = parseInt(qtyInput.value, 10);
      if (!quantidade || quantidade <= 0) {
        errors.push(`Informe uma quantidade válida para ${fullLabel}.`);
      }

      const item = { activity: key, modo, quantidade: quantidade || null };

      const competidores = collectCompetidores(subcard, quantidade, fullLabel, errors);
      if (competidores !== undefined) item.competidores = competidores;

      activities.push(item);
    });

    // Atividades de modo fixo (competições culturais) — cartão único, sem sub-cards.
    document.querySelectorAll('.activity-card[data-has-mode="false"]').forEach((card) => {
      const toggle = card.querySelector(".activity-toggle");
      if (!toggle.checked) return;

      const key = card.dataset.activity;
      const label = card.querySelector(".activity-card__header span").textContent;
      const qtyInput = card.querySelector(".input-quantidade");
      const quantidade = parseInt(qtyInput.value, 10);
      if (!quantidade || quantidade <= 0) {
        errors.push(`Informe uma quantidade válida para ${label}.`);
      }

      const item = { activity: key, quantidade: quantidade || null };

      const competidores = collectCompetidores(card, quantidade, label, errors);
      if (competidores !== undefined) item.competidores = competidores;

      activities.push(item);
    });

    if (activities.length === 0) {
      errors.push("Marque ao menos uma atividade.");
    }

    return { activities, errors };
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    hideBanners();

    const clientErrors = [];

    const pagamentoChecked = pagamentoGroup.querySelector("input:checked");
    if (!pagamentoChecked) {
      clientErrors.push("Informe a forma de pagamento (PIX ou Dinheiro).");
    }

    const { activities, errors: activityErrors } = collectActivitiesAndValidate();
    clientErrors.push(...activityErrors);

    if (clientErrors.length > 0) {
      showErrors(clientErrors);
      return;
    }

    const formData = new FormData();
    if (photoInput.files[0]) {
      formData.append("photo", photoInput.files[0]);
    }
    formData.append("forma_pagamento", pagamentoChecked.value);
    formData.append("activities_json", JSON.stringify(activities));

    submitBtn.disabled = true;
    submitBtn.textContent = "Enviando...";

    try {
      const response = await fetch("/submit", { method: "POST", body: formData });
      const data = await response.json();

      if (data.ok) {
        successId.textContent = data.purchase_id;

        const avisos = data.avisos || [];
        successWarnings.innerHTML = "";
        if (avisos.length > 0) {
          avisos.forEach((msg) => {
            const li = document.createElement("li");
            li.textContent = msg;
            successWarnings.appendChild(li);
          });
          successWarnings.hidden = false;
        } else {
          successWarnings.hidden = true;
        }

        successBanner.hidden = false;
        form.hidden = true;
        successBanner.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        showErrors(data.errors || ["Erro desconhecido ao enviar. Tente novamente."]);
      }
    } catch (err) {
      showErrors(["Falha de conexão. Verifique a internet e tente novamente."]);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Enviar compra";
    }
  });

  newSubmissionBtn.addEventListener("click", () => {
    form.reset();
    form.hidden = false;
    stepPhoto.hidden = false;
    resetPhotoStep();
    document.querySelectorAll(".activity-card__body, .activity-subcard__body").forEach((b) => (b.hidden = true));
    document.querySelectorAll(".activity-card, .activity-subcard").forEach((c) => {
      c.classList.remove("activity-card--active", "activity-subcard--active");
    });
    document.querySelectorAll(".qty-stepper").forEach((s) => resetStepper(s));
    document.querySelectorAll(".competitor-names__list").forEach((l) => (l.innerHTML = ""));
    document.querySelectorAll('[data-role="competidores"]').forEach((c) => (c.hidden = true));
    hideBanners();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});
