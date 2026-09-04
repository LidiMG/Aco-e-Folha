// Service worker mínimo — só o necessário para o Android considerar o site "instalável".
// Não faz cache agressivo de nada porque o app sempre precisa de internet
// para gravar no Google Sheets/Drive.

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  // Passa direto para a rede — sem cache offline por enquanto.
  event.respondWith(fetch(event.request));
});
