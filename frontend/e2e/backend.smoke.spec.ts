import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";

// Run only against e2e/start-backend.mjs's temporary database, never an external service.
test("real backend: isolated login, history, refresh and authorization", async ({
  page,
  request,
}) => {
  const username = `qa_${randomUUID().slice(0, 12)}`;
  const login = await request.post("/api/v1/auth/login", {
    data: { username },
  });
  expect(login.status()).toBe(200);
  const { access_token: token } = await login.json();
  expect(typeof token).toBe("string");
  await page.addInitScript(
    (token) => localStorage.setItem("token", token),
    token,
  );
  const history = page.waitForResponse(
    (r) => new URL(r.url()).pathname === "/api/v1/chat/threads",
  );
  await page.goto("/");
  expect((await history).status()).toBe(200);
  await expect(page.getByText(username, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(username, { exact: true }).first()).toBeVisible();
  const anonymous = await request.get("/api/v1/chat/threads");
  expect(anonymous.status()).toBe(401);
  // This smoke proves authentication/HTTP integration only; no real provider invocation.
});
