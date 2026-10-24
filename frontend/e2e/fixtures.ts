import { test as base, expect, type Page } from "@playwright/test";
import { createServer, type ServerResponse } from "node:http";

export const frame = (
  type: string,
  data: Record<string, unknown>,
  sequence: number,
) =>
  `id: ${sequence}\nevent: ${type}\ndata: ${JSON.stringify({ type, run_id: "qa-run", sequence, ...data })}\n\n`;

export async function seed(
  page: Page,
  authenticated = false,
  configured = true,
) {
  await page.addInitScript(
    ({ authenticated, configured }) => {
      if (authenticated) localStorage.setItem("token", "qa-dummy-token");
      if (configured)
        localStorage.setItem(
          "lobe-api-keys-storage",
          JSON.stringify({
            version: 1,
            state: {
              config: { openai: { enabled: true, apiKey: "qa-dummy-key" } },
            },
          }),
        );
    },
    { authenticated, configured },
  );
}

export async function send(page: Page, text = "QA question") {
  await page.getByPlaceholder("输入消息...").fill(text);
  await page.getByRole("button", { name: "Send", exact: true }).click();
}

export async function sessions(page: Page) {
  const open = page.getByRole("button", { name: "打开会话列表" });
  if (await open.isVisible()) await open.click();
}

export const test = base.extend<{ diagnostics: void }>({
  diagnostics: [
    async ({ page }, use, testInfo) => {
      const diagnostics: string[] = [];
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.name));
      // Deliberately omit message text, query strings, headers and bodies.
      page.on("console", (message) => {
        if (message.type() === "error") diagnostics.push("console:error");
      });
      page.on("response", (response) => {
        const url = new URL(response.url());
        if (url.pathname.startsWith("/api/") && response.status() >= 400)
          diagnostics.push(
            `${response.request().method()} ${url.pathname.replace(/\/[a-z0-9-]{20,}/gi, "/:id")} ${response.status()}`,
          );
      });
      await use();
      await testInfo.attach("safe-diagnostics", {
        body: Buffer.from(
          [...diagnostics, ...errors.map((e) => `pageerror:${e}`)].join("\n"),
        ),
        contentType: "text/plain",
      });
      expect(errors, "uncaught browser exceptions").toEqual([]);
    },
    { auto: true },
  ],
});
export { expect };

export async function mockApi(
  page: Page,
  options: {
    threads?: string[];
    history?: { role: string; content: string }[];
    deleteStatus?: number;
  } = {},
) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/users/me")
      return route.fulfill({
        json: {
          id: 101,
          username: "QA User",
          avatar_url: null,
          bangumi_id: null,
          sign: null,
          created_at: "2026-01-01T00:00:00Z",
        },
      });
    if (path.includes("/dashboard/"))
      return route.fulfill({ json: { total: 0, media_counts: {} } });
    if (path === "/api/v1/chat/threads")
      return route.fulfill({ json: { threads: options.threads ?? [] } });
    if (
      path === "/api/v1/chat/history" ||
      path.startsWith("/api/v1/chat/history/")
    ) {
      if (request.method() === "DELETE")
        return route.fulfill({
          status: options.deleteStatus ?? 200,
          json: { detail: "QA delete response" },
        });
      const thread = new URL(request.url()).searchParams.get("thread_id");
      return route.fulfill({
        json: {
          messages: options.threads?.includes(thread ?? "")
            ? (options.history ?? [])
            : [],
        },
      });
    }
    if (path === "/api/v1/chat")
      return route.fulfill({
        contentType: "text/event-stream",
        body:
          frame("message_chunk", { content: "QA answer" }, 1) +
          frame("message_end", { durable: false }, 2),
      });
    throw new Error(`Unmocked API: ${request.method()} ${path}`);
  });
  // Keep remote avatars/fonts out of deterministic tests.
  await page.route(/^https:\/\//, (route) =>
    route.fulfill({ status: 200, body: "" }),
  );
}

// A real HTTP response in controlled phases: route.fulfill alone buffers all SSE.
export async function streamingApi(page: Page, durable = false) {
  let response: ServerResponse | undefined;
  let connectedResolve!: () => void;
  const connected = new Promise<void>((resolve) => {
    connectedResolve = resolve;
  });
  const server = createServer((request, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "*");
    if (request.method === "OPTIONS") {
      res.end();
      return;
    }
    response = res;
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
    });
    res.write(
      frame(
        "message_input",
        { durable, role: "user", content: "QA question" },
        1,
      ),
    );
    connectedResolve();
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string")
    throw new Error("No mock server port");
  await page.route("**/api/v1/chat", (route) =>
    route.continue({ url: `http://127.0.0.1:${address.port}/api/v1/chat` }),
  );
  return {
    connected,
    write: (type: string, data: Record<string, unknown>, sequence: number) =>
      response?.write(frame(type, data, sequence)),
    end: () => response?.end(),
    close: async () => {
      response?.destroy();
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}
