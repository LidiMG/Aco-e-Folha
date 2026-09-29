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
  const newSubmissionBtn = document.getElementById("newSubmissionBtn");
  const photoInput = document.getElementById("photoInput");
  const photoPreview = document.getElementById("photoPreview");
  const retakePhotoBtn = document.getElementById("retakePhotoBtn");
  const cameraTrigger = document.querySelector(".camera-trigger");
  const stepPhoto = document.getElementById("stepPhoto");
  const pagamentoGroup = document.querySelector('[data-role="pagamento"]');
  const totalValueEl = document.getElementById("totalValue");

  // --- Código da compra (v2) ------------------------------------------------
  // Criado aqui, antes do envio, e reaproveitado em qualquer nova tentativa
  // da MESMA compra. Se a primeira tentativa chegou ao servidor mas a
  // resposta se perdeu, a segunda é reconhecida e não vira duplicata.
  // Só muda ao tocar em "Registrar nova compra".
  function novoIdCompra() {
    const bytes = new Uint8Array(4);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  let compraId = novoIdCompra();

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
    const collectsCla = container.dataset.collectsCla !== "false";

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

      entry.appendChild(nomeInput);
      entry.appendChild(telInput);

      if (collectsCla) {
        const claInput = document.createElement("input");
        claInput.type = "text";
        claInput.className = "input-competidor-cla";
        claInput.placeholder = "Clã (opcional)";
        entry.appendChild(claInput);
      }

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
    photoInput._fotoPronta = null;
    photoPreview.src = "";
    photoPreview.hidden = true;
    cameraTrigger.hidden = false;
    retakePhotoBtn.hidden = true;
  }

  photoInput.addEventListener("change", () => {
    window.prepararFoto(photoInput);
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
    const competidores = entries.map((entry) => {
      const claInput = entry.querySelector(".input-competidor-cla");
      return {
        nome: entry.querySelector(".input-competidor-nome").value.trim(),
        telefone: entry.querySelector(".input-competidor-telefone").value.trim(),
        cla: claInput ? claInput.value.trim() : "",
      };
    });
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

    submitBtn.disabled = true;

    const formData = new FormData();
    if (photoInput.files[0]) {
      // v2: a foto já sai comprimida do celular (~0,4MB em vez de 5-8MB),
      // e a compressão começou assim que ela foi tirada.
      submitBtn.textContent = "Preparando foto...";
      const foto = await window.fotoPronta(photoInput);
      formData.append("photo", foto);
    }
    submitBtn.textContent = "Enviando...";
    formData.append("forma_pagamento", pagamentoChecked.value);
    formData.append("activities_json", JSON.stringify(activities));
    formData.append("purchase_id", compraId);

    try {
      const response = await fetch("/submit", { method: "POST", body: formData });
      const data = await response.json();

      if (data.ok) {
        limparRascunho();
        successId.textContent = data.ja_registrada
          ? `${data.purchase_id} (a tentativa anterior já tinha sido registrada — não foi duplicada)`
          : data.purchase_id;
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
    limparRascunho();
    compraId = novoIdCompra();
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

  // --- Rascunho da compra (v2) ----------------------------------------------
  // Em celulares com pouca memória, o Android pode fechar o navegador enquanto
  // a câmera está aberta — ao voltar, a página recarrega vazia (era a "tela
  // branca" de um dos atendentes no evento). Agora tudo que foi preenchido
  // fica guardado no próprio aparelho e é restaurado; só a foto precisa ser
  // tirada de novo (navegadores não permitem guardar o arquivo da foto).
  const CHAVE_RASCUNHO = "aquisicao_rascunho";
  const VALIDADE_RASCUNHO_MS = 30 * 60 * 1000; // 30 minutos

  function containerKey(container) {
    return `${container.dataset.activity}|${container.dataset.modo || "fixo"}`;
  }

  function containersDeAtividade() {
    return document.querySelectorAll('.activity-subcard, .activity-card[data-has-mode="false"]');
  }

  function salvarRascunho() {
    try {
      const pagamento = pagamentoGroup.querySelector("input:checked");
      const itens = [];
      containersDeAtividade().forEach((container) => {
        const toggle = container.querySelector(".activity-toggle");
        if (!toggle || !toggle.checked) return;
        const competidores = Array.from(container.querySelectorAll(".competitor-entry")).map((entry) => {
          const cla = entry.querySelector(".input-competidor-cla");
          return {
            nome: entry.querySelector(".input-competidor-nome").value,
            telefone: entry.querySelector(".input-competidor-telefone").value,
            cla: cla ? cla.value : "",
          };
        });
        itens.push({
          chave: containerKey(container),
          quantidade: parseInt(container.querySelector(".input-quantidade").value, 10) || 0,
          competidores,
        });
      });
      if (!pagamento && itens.length === 0) {
        localStorage.removeItem(CHAVE_RASCUNHO);
        return;
      }
      localStorage.setItem(CHAVE_RASCUNHO, JSON.stringify({
        salvoEm: Date.now(),
        compraId,
        pagamento: pagamento ? pagamento.value : null,
        itens,
      }));
    } catch (err) {
      // sem espaço ou armazenamento bloqueado: segue sem rascunho
    }
  }

  function limparRascunho() {
    try { localStorage.removeItem(CHAVE_RASCUNHO); } catch (err) { /* ignora */ }
  }

  function restaurarRascunho() {
    let rascunho;
    try {
      rascunho = JSON.parse(localStorage.getItem(CHAVE_RASCUNHO) || "null");
    } catch (err) {
      return;
    }
    if (!rascunho) return;
    if (Date.now() - rascunho.salvoEm > VALIDADE_RASCUNHO_MS) {
      limparRascunho();
      return;
    }

    if (/^[0-9a-f]{8}$/.test(rascunho.compraId || "")) compraId = rascunho.compraId;

    const porChave = {};
    containersDeAtividade().forEach((container) => { porChave[containerKey(container)] = container; });

    (rascunho.itens || []).forEach((item) => {
      const container = porChave[item.chave];
      if (!container) return;
      const toggle = container.querySelector(".activity-toggle");
      toggle.checked = true;
      toggle.dispatchEvent(new Event("change", { bubbles: true }));
      const stepper = container.querySelector(".qty-stepper");
      if (stepper) setStepperValue(stepper, item.quantidade); // cria os campos dos competidores
      const entries = container.querySelectorAll(".competitor-entry");
      (item.competidores || []).forEach((comp, i) => {
        const entry = entries[i];
        if (!entry) return;
        entry.querySelector(".input-competidor-nome").value = comp.nome || "";
        entry.querySelector(".input-competidor-telefone").value = comp.telefone || "";
        const cla = entry.querySelector(".input-competidor-cla");
        if (cla) cla.value = comp.cla || "";
      });
    });

    if (rascunho.pagamento) {
      const radio = pagamentoGroup.querySelector(`input[value="${rascunho.pagamento}"]`);
      if (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }

    updateTotal();
    salvarRascunho(); // regrava completo (durante a restauração ele foi salvo pela metade)

    const aviso = document.createElement("div");
    aviso.className = "banner banner--info";
    aviso.textContent = "Recuperamos o que estava preenchido. Se a compra for PIX, tire a foto do comprovante de novo.";
    form.parentNode.insertBefore(aviso, form);
  }

  // Salva a cada mudança e, principalmente, logo antes de abrir a câmera.
  form.addEventListener("input", salvarRascunho);
  form.addEventListener("change", salvarRascunho);
  form.addEventListener("click", salvarRascunho);
  photoInput.addEventListener("click", salvarRascunho);

  restaurarRascunho();
});
