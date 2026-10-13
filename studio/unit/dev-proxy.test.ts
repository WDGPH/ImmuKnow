import { fileURLToPath } from "node:url";
import { createServer, resolveConfig, type ViteDevServer } from "vite";
import { expect, test, vi } from "vitest";

test("a stripping notebook proxy serves modules and connects HMR without changing build URLs", async () => {
  const root = fileURLToPath(new URL("../", import.meta.url));
  const configFile = `${root}vite.config.ts`;
  const prefix = "/notebook/example/proxy/5173/";
  vi.stubEnv("IMMUKNOW_DEV_PROXY_BASE", prefix);
  let server: ViteDevServer | undefined;
  let socket: WebSocket | undefined;
  try {
    const build = await resolveConfig({ root, configFile, logLevel: "silent" }, "build");
    expect(build.base).toBe("./");
    server = await createServer({
      root,
      configFile,
      logLevel: "silent",
      server: { host: "127.0.0.1", port: 0, strictPort: true, watch: null },
      optimizeDeps: { noDiscovery: true, include: [] },
    });
    await server.listen();
    const address = server.httpServer?.address();
    if (!address || typeof address === "string") throw new Error("Expected a TCP dev server");
    const port = address.port;
    const origin = `http://127.0.0.1:${port}`;
    // These are the upstream paths after the notebook removes its prefix.
    const html = await fetch(`${origin}/`);
    expect(html.status).toBe(200);
    expect(await html.text()).toContain(`src="${prefix}@vite/client"`);
    for (const path of ["/@vite/client", "/src/main.ts", "/src/style.css?import"]) {
      const response = await fetch(origin + path);
      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toContain("javascript");
    }
    // Also accept a request whose proxy preserved the prefix.
    const prefixed = await fetch(`${origin}${prefix}@vite/client`);
    expect(prefixed.status).toBe(200);
    expect(prefixed.headers.get("content-type")).toContain("javascript");
    socket = new WebSocket(
      `ws://127.0.0.1:${port}/?token=${server.config.webSocketToken}`,
      "vite-hmr",
    );
    const connected = await new Promise<string>((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Proxy HMR did not connect")), 5_000);
      socket?.addEventListener(
        "message",
        (event) => {
          clearTimeout(timeout);
          resolve(String(event.data));
        },
        { once: true },
      );
      socket?.addEventListener(
        "error",
        () => {
          clearTimeout(timeout);
          reject(new Error("Proxy HMR connection failed"));
        },
        { once: true },
      );
    });
    expect(JSON.parse(connected)).toEqual({ type: "connected" });
  } finally {
    socket?.close();
    await server?.close();
    vi.unstubAllEnvs();
  }
}, 15_000);
