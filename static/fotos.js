// fotos.js — compressão de foto no próprio celular, antes de enviar (v2).
//
// No evento da v1, cada foto saía do celular com 5 a 8MB e só o servidor
// comprimia. Com várias pessoas enviando ao mesmo tempo, isso deixava tudo
// lento (upload pesado na rede do evento + processador fraco do plano
// gratuito do Render). Agora a foto já sai do celular com ~0,7MB.
//
// Usada pela Aquisição (comprovante PIX) e pela pontuação do Arco/Machado
// (foto do alvo). Se algo der errado aqui, devolve o arquivo original —
// o servidor ainda sabe comprimir, então o envio nunca trava por causa disso.

(function () {
  const LADO_MAXIMO = 1600;        // pixels no lado maior (igual ao servidor)
  const TAMANHO_ALVO = 700 * 1000; // ~0,7MB
  const QUALIDADE_MINIMA = 0.35;

  function carregarImagem(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("Não foi possível ler a imagem."));
      };
      img.src = url;
    });
  }

  function canvasParaBlob(canvas, qualidade) {
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", qualidade));
  }

  window.comprimirFoto = async function (file) {
    if (!file) return file;
    try {
      const img = await carregarImagem(file);
      const escala = Math.min(1, LADO_MAXIMO / Math.max(img.naturalWidth, img.naturalHeight));
      const largura = Math.round(img.naturalWidth * escala);
      const altura = Math.round(img.naturalHeight * escala);

      const canvas = document.createElement("canvas");
      canvas.width = largura;
      canvas.height = altura;
      canvas.getContext("2d").drawImage(img, 0, 0, largura, altura);

      let qualidade = 0.85;
      let blob = await canvasParaBlob(canvas, qualidade);
      while (blob && blob.size > TAMANHO_ALVO && qualidade > QUALIDADE_MINIMA) {
        qualidade -= 0.1;
        blob = await canvasParaBlob(canvas, qualidade);
      }
      if (!blob) return file;

      const nome = (file.name || "foto").replace(/\.[^.]+$/, "") + ".jpg";
      return new File([blob], nome, { type: "image/jpeg" });
    } catch (err) {
      return file; // o servidor comprime no lugar
    }
  };
})();
