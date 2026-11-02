// resultados.js — desempate do Arco e do Machado (v3), em Resultados.
// Só é carregado quando quem está vendo é da organização ou da
// administração e há empate valendo pódio.
document.addEventListener("DOMContentLoaded", () => {
  const tela = document.getElementById("telaResultado");
  const errorBanner = document.getElementById("errorBanner");
  const errorList = document.getElementById("errorList");

  function mostrarErros(mensagens) {
    errorList.innerHTML = "";
    mensagens.forEach((m) => {
      const li = document.createElement("li");
      li.textContent = m;
      errorList.appendChild(li);
    });
    errorBanner.hidden = false;
    errorBanner.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  document.querySelectorAll(".desempate-grupo").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorBanner.hidden = true;
      const itens = Array.from(form.querySelectorAll(".desempate-grupo__linha")).map((linha) => ({
        row: parseInt(linha.dataset.row, 10),
        id_inscricao: linha.dataset.id || "",
        nome: linha.dataset.nome || "",
        ordem: linha.querySelector(".input-ordem").value.trim(),
      }));
      const botao = form.querySelector("button[type=submit]");
      botao.disabled = true;
      botao.textContent = "Salvando...";
      try {
        const dados = await window.enviarAoServidor(`/competicoes/${tela.dataset.key}/desempate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ itens }),
        });
        if (dados.ok) {
          location.reload();
          return;
        }
        mostrarErros(dados.errors || ["Erro desconhecido ao salvar. Tente novamente."]);
      } catch (err) {
        mostrarErros([err.message || "Falha de conexão.", "Toque em Salvar desempate de novo."]);
      }
      botao.disabled = false;
      botao.textContent = "Salvar desempate";
    });
  });
});
