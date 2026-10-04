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
  // 交易记录现在位于「交易记录 / 现金与事件 / 导入批次」标签页中
  return page.locator("#pane-transactions tr.el-table__row", { hasText: code });
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

test("CSV 导入：预览确认入账，重复导入全部跳过", async ({ page }) => {
  const csv = [
    "成交日期,证券代码,证券名称,业务名称,成交价格,成交数量,成交金额,手续费,成交编号",
    "2026-06-01,600519,贵州茅台,证券买入,1500,10,15000,5,E2E001",
  ].join("\n");

  await page.goto("/portfolio");
  await page.locator('input[type="file"][accept*=".csv"]').setInputFiles({
    name: "delivery.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf-8"),
  });

  const dialog = page.locator(".el-dialog", { hasText: "核对 CSV 导入内容" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("中信证券成交明细");
  await expect(dialog).toContainText("共 1 行");

  await dialog.getByRole("button", { name: /确认导入 1 行/ }).click();

  const result = page.locator(".el-dialog", { hasText: "导入结果与持仓核对" });
  await expect(result).toBeVisible();
  await expect(result).toContainText("导入 1 行");
  await expect(result).toContainText("600519");
  await result.locator(".el-dialog__headerbtn").click();

  // 再次上传同一文件：全部判重，确认按钮禁用
  await page.locator('input[type="file"][accept*=".csv"]').setInputFiles({
    name: "delivery.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf-8"),
  });
  const again = page.locator(".el-dialog", { hasText: "核对 CSV 导入内容" });
  await expect(again).toContainText("重复 1");
  await expect(again.getByRole("button", { name: /确认导入 0 行/ })).toBeDisabled();

  // 账户收益面板渲染正常（含 TWR / XIRR 口径）
  await again.getByRole("button", { name: "取消" }).click();
  const accountPanel = panel(page, "账户收益（现金 + 持仓）");
  await expect(accountPanel).toBeVisible();
  await expect(accountPanel).toContainText("时间加权收益率 (TWR)");
  await expect(accountPanel).toContainText("资金加权收益率 (XIRR)");
  // 无指数行情时基准对比显式降级提示
  await expect(accountPanel).toContainText("基准对比");
  await expect(accountPanel).toContainText("暂无历史行情");
});

test("数据健康：对账结果结构化展示，失败时可重试", async ({ page }) => {
  const reconcileFixture = {
    fund_code: "000001",
    status: "warning",
    summary: "最近 2 条对账记录，发现 1 个差异信号",
    source_errors: { akshare: null, eastmoney: null },
    counts: { akshare_missing: 1, eastmoney_missing: 0, unit_nav_diff: 0, daily_return_diff: 0 },
    rows: [
      {
        nav_date: "2026-01-05T00:00:00",
        akshare_unit_nav: null,
        eastmoney_unit_nav: 1.2345,
        unit_nav_diff: null,
        akshare_daily_return: null,
        eastmoney_daily_return: 0.5,
        daily_return_diff: null,
        status: "AKShare 缺失",
      },
      {
        nav_date: "2026-01-02T00:00:00",
        akshare_unit_nav: 1.2346,
        eastmoney_unit_nav: 1.2346,
        unit_nav_diff: 0,
        akshare_daily_return: 0.5,
        eastmoney_daily_return: 0.5,
        daily_return_diff: 0,
        status: "一致",
      },
    ],
  };
  await page.route("**/api/v1/watchlist", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { fund_code: "000001", fund_name: "测试基金", is_active: true },
      ]),
    }),
  );
  let reconcileCalls = 0;
  await page.route(/\/api\/v1\/data\/reconcile\//, (route) => {
    reconcileCalls += 1;
    if (reconcileCalls > 1) {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "对账服务不可用" }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(reconcileFixture),
    });
  });

  await page.goto("/data-health");
  await page.locator(".el-select").first().click();
  await page.locator(".el-select-dropdown__item", { hasText: "000001" }).first().click();
  await page.getByRole("button", { name: "执行对账" }).click();

  // 结构化表格：不再裸 JSON，结论用标签展示
  await expect(page.getByText(reconcileFixture.summary)).toBeVisible();
  await expect(page.locator(".el-tag", { hasText: "AKShare 缺失" })).toBeVisible();
  await expect(page.locator(".el-tag", { hasText: "一致" })).toBeVisible();

  // 再次对账失败：内联错误态 + 重试按钮
  await page.getByRole("button", { name: "执行对账" }).click();
  await expect(page.getByText("对账失败")).toBeVisible();
  await expect(page.getByRole("button", { name: "重试" })).toBeVisible();
});

test("空数据页面展示可操作的空态", async ({ page }) => {
  await page.goto("/scores");
  await expect(page.getByText("暂无评分数据：先到自选池同步净值并计算评分")).toBeVisible();

  await page.goto("/score-trend");
  await expect(page.getByText("自选池为空，先添加基金")).toBeVisible();

  await page.goto("/market");
  await expect(page.getByText("暂无市场数据，点击下方按钮同步指数行情")).toBeVisible();
});

test("基金详情：部分板块失败时提示原因并可继续浏览", async ({ page }) => {
  await page.route("**/api/v1/funds/*/indicators", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "指标服务异常" }),
    }),
  );

  await page.goto("/funds/000001");

  await expect(page.getByText("部分板块加载失败（其余内容仍可查看）")).toBeVisible();
  await expect(page.getByText(/指标：指标服务异常/)).toBeVisible();
});

test("CSV 导入回滚：整批删除已入账流水与持仓", async ({ page }) => {
  const rollbackCode = `6${stamp}`;
  const csv = [
    "成交日期,证券代码,证券名称,业务名称,成交价格,成交数量,成交金额,手续费,成交编号",
    `2026-06-02,${rollbackCode},回滚测试,证券买入,1500,10,15000,5,E2E${stamp}RB`,
  ].join("\n");

  await page.goto("/portfolio");
  await page.locator('input[type="file"][accept*=".csv"]').setInputFiles({
    name: "rollback.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv, "utf-8"),
  });
  const dialog = page.locator(".el-dialog", { hasText: "核对 CSV 导入内容" });
  await dialog.getByRole("button", { name: /确认导入 1 行/ }).click();
  await page.locator(".el-dialog", { hasText: "导入结果与持仓核对" }).locator(".el-dialog__headerbtn").click();
  await expect(transactionRow(page, rollbackCode)).toHaveCount(1);
  await expect(positionRow(page, rollbackCode)).toHaveCount(1);

  // 在导入批次标签页回滚最新批次
  await page.getByRole("tab", { name: "导入批次" }).click();
  const batchRow = page.locator("#pane-imports tr.el-table__row").first();
  await batchRow.getByRole("button", { name: "整批回滚" }).click();
  const confirm = page.locator(".el-message-box");
  await expect(confirm).toContainText("整批回滚");
  await confirm.getByRole("button", { name: "确认回滚" }).click();
  await expect(page.locator(".el-message").last()).toContainText("已回滚");
  await expect(page.locator("#pane-imports tr.el-table__row").first()).toContainText("已回滚");

  // 流水与自动汇总持仓都已删除
  await page.getByRole("tab", { name: "交易记录" }).click();
  await expect(transactionRow(page, rollbackCode)).toHaveCount(0);
  await expect(positionRow(page, rollbackCode)).toHaveCount(0);
});
