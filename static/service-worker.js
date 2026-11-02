// Service worker mínimo — só o necessário para o app ser "instalável".
// v3: é servido na raiz do site (/service-worker.js), para cuidar de todas
// as páginas; antes ficava em /static/ e não cuidava de nenhuma.
//
// Não guarda nada em cache e não intercepta nenhum envio: o app sempre
// precisa de internet para gravar no Google Sheets/Drive, e cada requisição
// segue direto para a rede, como se o service worker não existisse.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
