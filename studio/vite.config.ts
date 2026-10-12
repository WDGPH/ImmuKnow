import { existsSync } from "node:fs";
import type { IncomingMessage } from "node:http";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => {
  const proxyBase = command === "serve" ? process.env.IMMUKNOW_DEV_PROXY_BASE : undefined;
  if (proxyBase && !/^\/(?:[\w.-]+\/)+$/.test(proxyBase)) {
    throw new Error("IMMUKNOW_DEV_PROXY_BASE must be a URL path with leading and trailing slashes.");
  }
  return {
    base: proxyBase || "./",
    plugins: proxyBase
      ? [{
          name: "notebook-proxy-base",
          configureServer(server) {
            // Notebook proxies strip their prefix before forwarding requests.
            // Restore it before Vite handles HTTP or HMR WebSocket routing.
            const restoreBase = (request: IncomingMessage) => {
              if (request.url && !request.url.startsWith(proxyBase)) {
                request.url = proxyBase + request.url.replace(/^\/+/, "");
              }
            };
            server.middlewares.use((request, _response, next) => {
              restoreBase(request);
              next();
            });
            server.httpServer?.prependListener("upgrade", restoreBase);
          },
        }]
      : [],
    worker: { format: "es" },
    build: {
      rolldownOptions: {
        input: { proof: "proof.html", ...(existsSync("index.html") ? { app: "index.html" } : {}) },
      },
    },
  };
});
