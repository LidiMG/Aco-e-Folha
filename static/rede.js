// rede.js — envio ao servidor com tratamento de erros (v2).
//
// Antes, qualquer problema (internet caindo, servidor reiniciando no Render,
// sessão de login expirada) aparecia como a mesma mensagem genérica de
// "falha de conexão", e um envio travado deixava o botão em "Enviando..."
// para sempre. Agora cada caso tem uma mensagem própria, e o envio tem um
// tempo-limite.

(function () {
  const TEMPO_LIMITE_MS = 60 * 1000; // o servidor desiste em ~45s; aqui damos folga

  class ErroDeEnvio extends Error {
    constructor(mensagem, tipo) {
      super(mensagem);
      this.tipo = tipo; // "offline", "tempo", "sessao", "servidor", "rede"
    }
  }

  window.ErroDeEnvio = ErroDeEnvio;

  // Envia e devolve o JSON da resposta. Se não houver resposta aproveitável,
  // lança ErroDeEnvio com uma mensagem pronta para mostrar na tela.
  window.enviarAoServidor = async function (url, opcoes) {
    if (navigator.onLine === false) {
      throw new ErroDeEnvio("O celular está sem internet no momento. Confira o Wi-Fi ou os dados móveis e tente de novo.", "offline");
    }

    const controle = new AbortController();
    const cronometro = setTimeout(() => controle.abort(), TEMPO_LIMITE_MS);
    let resposta;
    try {
      resposta = await fetch(url, Object.assign({}, opcoes, { signal: controle.signal }));
    } catch (err) {
      if (err.name === "AbortError") {
        throw new ErroDeEnvio("O envio demorou demais para responder (a rede pode estar lenta).", "tempo");
      }
      throw new ErroDeEnvio("Não foi possível falar com o servidor: a conexão caiu ou está instável.", "rede");
    } finally {
      clearTimeout(cronometro);
    }

    let dados = null;
    try {
      dados = await resposta.json();
    } catch (err) {
      dados = null; // veio uma página em vez de JSON (ex.: Render reiniciando)
    }

    if (resposta.status === 401) {
      throw new ErroDeEnvio("Sua sessão de login expirou.", "sessao");
    }
    if (!dados) {
      if (resposta.status >= 500) {
        throw new ErroDeEnvio("O servidor está reiniciando ou instável. Aguarde uns 30 segundos e tente de novo.", "servidor");
      }
      throw new ErroDeEnvio("O servidor respondeu de um jeito inesperado. Atualize a página e tente de novo.", "servidor");
    }
    return dados;
  };
})();
