import { expect, test, type Page } from "@playwright/test";

// Unique 6-digit codes so repeated runs never collide inside the scratch database.
const stamp = String(Date.now()).slice(-5);
const BUY_CODE = `9${stamp}`;
const FAIL_CODE = `8${stamp}`;
const PARTIAL_CODE = `7${stamp}`;

async function seedManualPosition(
  request: import("@playwright/test").APIRequestContext,
  code: string,
  share: string,
  amount: string,
) {
  const response = await request.post("/api/v1/portfolio", {
    data: {
      fund_code: code,
      holding_amount: amount,
      holding_share: share,
      cost_nav: "1",
      buy_date: "2026-01-01",
      note: "由中信证券持仓截图导入（2026-01-01）",
    },
  });
  expect(response.ok()).toBeTruthy();
}

function panel(page: Page, title: string) {
  return page
    .locator(".panel")
    .filter({ has: page.getByRole("heading", { name: title, exact: true }) })
    .first();
}

function positionRow(page: Page, code: string) {
  return panel(page, "统一持仓列表").locator("tr.el-table__row", { hasText: code });
}

function transactionRow(page: Page, code: string) {
  return panel(page, "交易记录").locator("tr.el-table__row", { hasText: code });
}

async function fillField(page: Page, label: string, value: string) {
  const item = page.locator(".el-form-item").filter({ hasText: label }).first();
  const input = item.locator("input").first();
  await input.fill(value);
  await input.press("Enter");
}

async function selectTradeType(page: Page, option: string) {
  const item = page.locator(".el-form-item").filter({ hasText: "交易类型" }).first();
  await item.locator(".el-select").click();
  await page.locator(".el-select-dropdown__item", { hasText: option }).first().click();
}

async function submit(page: Page, message: string) {
  await page.getByRole("button", { name: "保存并自动汇总" }).click();
  await expect(page.locator(".el-message").last()).toContainText(message);
}

test("录入交易：期初事件与持仓累加，刷新后一致", async ({ page, request }) => {
  // 预置一笔手工持仓（等同截图导入落库的结果），首笔交易应把它变成有日期的期初事件。
  await seedManualPosition(request, BUY_CODE, "1000", "1000");

  await page.goto("/portfolio");
  await expect(panel(page, "统一持仓列表")).toBeVisible();

  await fillField(page, "代码", BUY_CODE);
  await fillField(page, "交易日期", "2026-02-01");
  await fillField(page, "成交金额", "100");
  await fillField(page, "成交净值", "1");
  await submit(page, "交易记录已保存");

  await expect(positionRow(page, BUY_CODE)).toContainText("1100");
  await expect(transactionRow(page, BUY_CODE)).toHaveCount(2);
  await expect(transactionRow(page, BUY_CODE).filter({ hasText: "期初" })).toHaveCount(1);

  await page.reload();
  await expect(positionRow(page, BUY_CODE)).toContainText("1100");
  await expect(transactionRow(page, BUY_CODE)).toHaveCount(2);
  await expect(transactionRow(page, BUY_CODE).filter({ hasText: "期初" })).toHaveCount(1);
});

test("失败提示：超卖被拒绝并显示原因，刷新后账本不变", async ({ page }) => {
  await page.goto("/portfolio");
  await expect(panel(page, "统一持仓列表")).toBeVisible();

  await fillField(page, "代码", FAIL_CODE);
  await fillField(page, "交易日期", "2026-03-01");
  await fillField(page, "成交金额", "1000");
  await fillField(page, "成交净值", "1");
  await submit(page, "交易记录已保存");
  await expect(transactionRow(page, FAIL_CODE)).toHaveCount(1);

  await fillField(page, "代码", FAIL_CODE);
  await selectTradeType(page, "卖出");
  await fillField(page, "交易日期", "2026-01-01");
  await fillField(page, "成交金额", "1000");
  await fillField(page, "成交净值", "1");
  await page.getByRole("button", { name: "保存并自动汇总" }).click();
  await expect(page.locator(".el-message--error").last()).toContainText("卖出份额超过 2026-01-01");

  await expect(transactionRow(page, FAIL_CODE)).toHaveCount(1);
  await page.reload();
  await expect(transactionRow(page, FAIL_CODE)).toHaveCount(1);
  await expect(positionRow(page, FAIL_CODE)).toContainText("1000");
});

test("缺行情时展示估值完整性提示", async ({ page, request }) => {
  await seedManualPosition(request, PARTIAL_CODE, "1000", "1000");

  await page.goto("/portfolio");

  const warning = page.locator(".el-alert", { hasText: "组合估值不完整" });
  await expect(warning).toBeVisible();
  await expect(warning).toContainText(PARTIAL_CODE);
  await expect(warning).toContainText("缺少最新净值");
  await expect(positionRow(page, PARTIAL_CODE).locator(".el-tag", { hasText: "缺失" })).toBeVisible();
});

test("驾驶舱可一键创建今日批次并显示进度", async ({ page }) => {
  await page.goto("/");

  const panel = page
    .locator(".panel")
    .filter({ has: page.getByRole("heading", { name: "今日数据更新", exact: true }) })
    .first();
  await expect(panel).toBeVisible();

  await panel.getByRole("button", { name: "更新今日数据" }).click();

  // 无 worker 运行时批次停留在排队中，页面应显示批次号与进度条
  await expect(panel).toContainText("批次 #");
  await expect(panel.locator(".el-progress")).toBeVisible();

  // 重复点击返回同一批次（幂等），页面不会出现第二个批次提示
  await panel.getByRole("button", { name: "更新今日数据" }).click();
  await expect(page.locator(".el-message").last()).toContainText("已存在");
});
