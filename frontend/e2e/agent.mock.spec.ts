import {
  test,
  expect,
  mockApi,
  seed,
  send,
  sessions,
  streamingApi,
  frame,
} from "./fixtures";

test("empty, missing configuration, whitespace and guest refresh", async ({
  page,
}) => {
  await mockApi(page);
  await seed(page, false, false);
  await page.goto("/");
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
  await send(page, "   ");
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
  await send(page);
  await expect(
    page.getByRole("status").filter({ hasText: "configuration_error" }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
});

test("incremental stream, tool details and terminal success", async ({
  page,
}) => {
  await seed(page);
  await mockApi(page);
  const stream = await streamingApi(page);
  try {
    await page.goto("/");
    await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
    await send(page);
    await stream.connected;
    await expect(
      page.getByRole("button", { name: "Stop", exact: true }),
    ).toBeVisible();
    stream.write(
      "tool_call_start",
      {
        invocation_id: "qa-tool",
        capability: "get_current_time",
        argument_keys: [],
      },
      2,
    );
    await expect(
      page.getByText("正在调用工具...", { exact: false }).first(),
    ).toBeVisible();
    stream.write(
      "tool_call_end",
      {
        invocation_id: "qa-tool",
        capability: "get_current_time",
        output: "QA tool result",
        status: "succeeded",
        duration_ms: 12,
      },
      3,
    );
    stream.write("message_chunk", { content: "QA partial" }, 4);
    await expect(page.getByText("QA partial", { exact: true })).toBeVisible();
    stream.write("message_chunk", { content: " answer" }, 5);
    stream.write("message_end", { durable: false }, 6);
    stream.write("run_completed", { status: "succeeded" }, 7);
    stream.end();
    await expect(
      page.getByText("QA partial answer", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Send", exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Succeeded", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "隐藏思考与工具调用过程" }).click();
    await page.getByRole("button", { name: "显示思考与工具调用过程" }).click();
  } finally {
    await stream.close();
  }
});

test("backend error remains failed and next send recovers", async ({
  page,
}) => {
  await seed(page);
  await mockApi(page);
  let attempts = 0;
  await page.route("**/api/v1/chat", (route) => {
    attempts++;
    return attempts === 1
      ? route.fulfill({ status: 503, json: { detail: "QA unavailable" } })
      : route.fulfill({
          contentType: "text/event-stream",
          body:
            frame("message_chunk", { content: "QA recovered" }, 1) +
            frame("message_end", { durable: false }, 2),
        });
  });
  await page.goto("/");
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
  await send(page);
  await expect(
    page.getByRole("status").filter({ hasText: "Run failed" }),
  ).toBeVisible();
  await send(page, "retry safely");
  await expect(
    page.getByRole("article").getByText("QA recovered", { exact: true }),
  ).toBeVisible();
  expect(attempts).toBe(2);
});

test("authenticated history reload, search and create", async ({ page }) => {
  await seed(page, true);
  await mockApi(page, {
    threads: ["qa-thread"],
    history: [
      { role: "human", content: "QA persisted question" },
      { role: "assistant", content: "QA persisted answer" },
    ],
  });
  await page.goto("/");
  await expect(
    page.getByText("QA persisted answer", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("QA persisted answer", { exact: true }),
  ).toBeVisible();
  await sessions(page);
  await page.getByPlaceholder("搜索会话...").fill("no-such-title");
  await expect(page.getByRole("button", { name: "删除会话" })).toHaveCount(0);
  await page.getByPlaceholder("搜索会话...").fill("");
  await page
    .getByRole("button", { name: "\u65b0\u5efa\u4f1a\u8bdd", exact: true })
    .click();
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
});

test("failed delete retains session and exposes error", async ({ page }) => {
  await seed(page, true);
  await mockApi(page, {
    threads: ["qa-thread"],
    deleteStatus: 500,
    history: [{ role: "assistant", content: "QA retained answer" }],
  });
  await page.goto("/");
  await expect(
    page.getByText("QA retained answer", { exact: true }),
  ).toBeVisible();
  await sessions(page);
  await page.getByRole("button", { name: "删除会话" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "删除会话失败" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "删除会话" })).toHaveCount(1);
});

test("layout: composer actions fit viewport and mobile drawer closes", async ({
  page,
}, testInfo) => {
  await seed(page);
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
  const search = page.getByRole("button", { name: "搜索并插入" });
  await expect(search).toBeVisible();
  const box = await search.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  const sendButton = page.getByRole("button", { name: "Send", exact: true });
  // Wait for library styling rather than measuring the initial unstyled HTML.
  await expect(sendButton).toHaveCSS("height", "36px");
  const sendBox = await sendButton.boundingBox();
  expect(sendBox).not.toBeNull();
  await expect
    .poll(async () => {
      const box = await sendButton.boundingBox();
      return box ? box.y + box.height : Number.POSITIVE_INFINITY;
    })
    .toBeLessThanOrEqual(page.viewportSize()!.height);
  if (testInfo.project.name === "mobile") {
    await sessions(page);
    await expect(page.getByPlaceholder("搜索会话...")).toBeVisible();
    await page.getByRole("button", { name: "收起会话列表" }).click();
    await expect(page.getByPlaceholder("搜索会话...")).toBeHidden();
  }
  await page.screenshot({ path: testInfo.outputPath("layout.png") });
});

test("durable cancel waits for terminal event and retains partial answer", async ({
  page,
}) => {
  await seed(page, true);
  await mockApi(page);
  let cancels = 0;
  await page.route("**/api/v1/runs/qa-run/cancel", (route) => {
    cancels++;
    return route.fulfill({
      json: { run_id: "qa-run", cancellation_requested: true },
    });
  });
  const stream = await streamingApi(page, true);
  try {
    await page.goto("/");
    await expect(
      page.getByText("\u6ca1\u6709\u6d88\u606f", { exact: true }),
    ).toBeVisible();
    await send(page);
    await stream.connected;
    stream.write("message_chunk", { content: "QA before cancel" }, 2);
    await expect(
      page.getByRole("article").getByText("QA before cancel", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await expect.poll(() => cancels).toBe(1);
    await expect(
      page.getByRole("status").filter({ hasText: "Cancelling run" }),
    ).toBeVisible();
    stream.write("run.cancelled", { status: "cancelled" }, 3);
    stream.end();
    await expect(
      page.getByRole("status").filter({ hasText: "Run cancelled" }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("article").getByText("QA before cancel", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Send", exact: true }),
    ).toBeVisible();
  } finally {
    await stream.close();
  }
});

test("durable disconnect replays by cursor without resubmitting chat", async ({
  page,
}) => {
  await seed(page, true);
  await mockApi(page);
  let posts = 0;
  let after: string | null = null;
  await page.route("**/api/v1/chat", (route) => {
    posts++;
    return route.fulfill({
      contentType: "text/event-stream",
      body:
        frame(
          "message_input",
          { durable: true, role: "user", content: "QA question" },
          1,
        ) + frame("message_chunk", { content: "QA replay " }, 2),
    });
  });
  await page.route("**/api/v1/runs/qa-run/events?*", (route) => {
    after = new URL(route.request().url()).searchParams.get("after");
    return route.fulfill({
      json: {
        events: [
          {
            run_id: "qa-run",
            sequence: 2,
            event_type: "message_chunk",
            payload: { content: "QA replay " },
          },
          {
            run_id: "qa-run",
            sequence: 3,
            event_type: "message_chunk",
            payload: { content: "complete" },
          },
          {
            run_id: "qa-run",
            sequence: 4,
            event_type: "run.succeeded",
            payload: {},
          },
        ],
      },
    });
  });
  await page.goto("/");
  await expect(
    page.getByText("\u6ca1\u6709\u6d88\u606f", { exact: true }),
  ).toBeVisible();
  await send(page);
  await expect(
    page.getByText("QA replay complete", { exact: true }),
  ).toBeVisible();
  expect(posts).toBe(1);
  expect(after).toBe("2");
});

test("timeout terminal never becomes success and retains partial content", async ({
  page,
}) => {
  await seed(page);
  await mockApi(page);
  await page.route("**/api/v1/chat", (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body:
        frame("message_chunk", { content: "QA timeout partial" }, 1) +
        frame("run_failed", { status: "timeout", error_code: "timeout" }, 2),
    }),
  );
  await page.goto("/");
  await expect(
    page.getByText("\u6ca1\u6709\u6d88\u606f", { exact: true }),
  ).toBeVisible();
  await send(page);
  await expect(
    page.getByRole("status").filter({ hasText: "Run timed out" }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("QA timeout partial", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Send", exact: true }),
  ).toBeVisible();
});

test("saved dark theme hydrates without losing preference", async ({
  page,
}) => {
  await seed(page);
  await mockApi(page);
  await page.addInitScript(() =>
    localStorage.setItem("APP_THEME_APPEARANCE", "dark"),
  );
  await page.goto("/");
  await expect(
    page.getByText("\u6ca1\u6709\u6d88\u606f", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("\u6ca1\u6709\u6d88\u606f", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.getItem("APP_THEME_APPEARANCE")),
  ).toBe("dark");
});
test("auth invalidation detaches a live stream and removes previous-user display", async ({
  page,
}) => {
  await seed(page, true);
  await mockApi(page);
  let cancellationRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/cancel"))
      cancellationRequests++;
  });
  const stream = await streamingApi(page, true);
  try {
    await page.goto("/");
    await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
    await send(page);
    await stream.connected;
    stream.write("message_chunk", { content: "QA previous-user content" }, 2);
    await expect(
      page
        .getByRole("article")
        .getByText("QA previous-user content", { exact: true }),
    ).toBeVisible();
    await page.evaluate(() => {
      localStorage.removeItem("token");
      window.dispatchEvent(new Event("otakuneko-auth-state-changed"));
    });
    await expect(page.getByText("没有消息", { exact: true })).toBeVisible();
    stream.write("message_chunk", { content: "QA late content" }, 3);
    stream.end();
    await expect(page.getByRole("article")).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Send", exact: true }),
    ).toBeVisible();
    expect(cancellationRequests).toBe(0);
  } finally {
    await stream.close();
  }
});
