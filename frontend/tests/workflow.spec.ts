import { expect, Page, test } from "@playwright/test";

const accounts = {
  sales: ["sales@cwg.local", "SalesDemo!2026"],
  procurement: ["procurement@cwg.local", "ProcDemo!2026"],
  manager: ["manager@cwg.local", "ManagerDemo!2026"],
} as const;

async function login(page: Page, role: keyof typeof accounts) {
  const [email, password] = accounts[role];
  await page.goto("/login");
  await page.getByLabel("邮箱").fill(email);
  await page.getByLabel("密码").fill(password);
  await page.getByRole("button", { name: "进入工作台" }).click();
  await expect(page).toHaveURL("http://localhost:3000/");
  await expect(page.getByText("报价决策中心")).toBeVisible();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test("sales quote, manager approval, PDF and procurement visibility", async ({ page }) => {
  await login(page, "sales");
  const forbidden = await page.request.get("/api/backend/supplier-costs");
  expect(forbidden.status()).toBe(403);

  const inquiryResponse = await page.request.post("/api/backend/inquiries", {
    data: {
      raw_text: "我们是华东汽车科技。请对S4-1003报价360件，纸箱包装，发往上海，贸易条款DDP，币种CNY。",
    },
  });
  expect(inquiryResponse.ok()).toBeTruthy();
  const inquiry = await inquiryResponse.json();
  const processResponse = await page.request.post(`/api/backend/inquiries/${inquiry.id}/process`);
  const result = await processResponse.json();
  expect(result.status).toBe("draft");

  await page.goto(`/quotes/${result.quote_id}`);
  await expect(page.getByRole("heading", { name: /S4-1003/ })).toBeVisible();
  await expect(page.getByText("内部价格分析")).toHaveCount(0);
  await page.getByRole("button", { name: "提交经理审批" }).click();
  await expect(page.getByText("待审批")).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/sales-quote-desktop.png", fullPage: true });

  await logout(page);
  await login(page, "manager");
  await page.goto(`/quotes/${result.quote_id}`);
  await expect(page.getByText("内部价格分析")).toBeVisible();
  await page.getByPlaceholder("例外报价或驳回时填写审批理由").fill("标准报价，证据与成本均有效");
  await page.getByRole("button", { name: "批准" }).click();
  await expect(page.getByText("已批准")).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载最终 PDF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/quote-.+-v\d+\.pdf/);

  await logout(page);
  await login(page, "procurement");
  await page.goto("/costs");
  await expect(page.getByRole("heading", { name: "供应商成本" })).toBeVisible();
  await expect(page.getByText("已过期").first()).toBeVisible();
});

test("missing currency pauses and resumes from the correction screen", async ({ page }) => {
  await login(page, "sales");
  const inquiryResponse = await page.request.post("/api/backend/inquiries", {
    data: {
      raw_text: "我们是远航智能汽车。请对S4-1004报价380件，纸箱包装，发往宁波，贸易条款DAP。",
    },
  });
  const inquiry = await inquiryResponse.json();
  const processResponse = await page.request.post(`/api/backend/inquiries/${inquiry.id}/process`);
  const paused = await processResponse.json();
  expect(paused.status).toBe("needs_clarification");
  expect(paused.extracted.missing_fields).toEqual(["currency"]);

  await page.goto(`/inquiries/${inquiry.id}`);
  await expect(page.getByText("需要人工确认")).toBeVisible();
  await page.getByLabel("币种").fill("CNY");
  await page.getByRole("button", { name: "保存并继续报价" }).click();
  await expect(page).toHaveURL(/\/quotes\//);
  await expect(page.getByRole("heading", { name: /S4-1004/ })).toBeVisible();
});

test("mobile dashboard and navigation remain usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "manager");
  await page.screenshot({ path: "test-results/screenshots/manager-dashboard-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "打开导航" }).click();
  await expect(page.getByRole("link", { name: /RAG 评测/ })).toBeVisible();
  await page.getByRole("link", { name: /RAG 评测/ }).click();
  await expect(page.getByRole("heading", { name: "RAG 评测" })).toBeVisible();
});

test("knowledge answer is direct, cited and keeps hybrid evidence available", async ({ page }) => {
  await login(page, "sales");
  await page.goto("/knowledge");
  await page.getByRole("button", { name: "问答", exact: true }).click();
  await page.getByLabel("业务问题").fill("S4-1000 长途发货时怎样避免水汽和磕碰");
  await page.getByRole("button", { name: "生成确切答案" }).click();
  await expect(page.getByText("已核验引用")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/防潮|缓冲|防静电/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /\[1\].*S4-1000/ })).toBeVisible();
  await page.getByText(/查看证据原文与检索轨迹/).click();
  await expect(page.getByText(/Dense #/).first()).toBeVisible();
  await expect(page.getByText(/BM25 #/).first()).toBeVisible();
  await expect(page.getByText(/RRF 0\./).first()).toBeVisible();
  await expect(page.getByText(/nomic-embed-text/).first()).toBeVisible();
  await page.screenshot({
    path: "test-results/screenshots/ollama-hybrid-search.png",
    fullPage: true,
  });
});
