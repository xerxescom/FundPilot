<template>
  <div v-loading="loading" element-loading-text="正在更新持仓和组合诊断...">
    <div class="panel screenshot-import">
      <div class="section-heading">
        <div>
          <h2 class="section-title">中信证券持仓截图导入</h2>
          <p class="muted">识别结果会先生成可编辑草稿；确认后只更新没有交易流水的手工持仓，原图不会保存。</p>
        </div>
        <el-upload accept="image/png,image/jpeg,image/webp" :auto-upload="false" :show-file-list="false" :on-change="recognizeHoldingScreenshot">
          <el-button type="primary" :loading="recognizing">上传截图并识别</el-button>
        </el-upload>
      </div>
    </div>

    <div class="panel screenshot-import">
      <div class="section-heading">
        <div>
          <h2 class="section-title">交易与资金流水 CSV 导入</h2>
          <p class="muted">支持中信证券成交明细与资金流水（CSV / 制表符，UTF-8 或 GBK）。导入前可核对列映射与每一行，重复行自动跳过。</p>
        </div>
        <el-upload accept=".csv,.txt,text/csv" :auto-upload="false" :show-file-list="false" :on-change="previewCsvImport">
          <el-button :loading="previewingImport">上传 CSV 并预览</el-button>
        </el-upload>
      </div>
    </div>

    <div class="panel">
      <h2 class="section-title">记录交易</h2>
      <el-form :model="transaction" inline>
        <el-form-item label="资产类型">
          <el-select v-model="transaction.asset_type" class="type-select">
            <el-option label="基金" value="fund" />
            <el-option label="股票" value="stock" />
            <el-option label="ETF" value="etf" />
          </el-select>
        </el-form-item>
        <el-form-item label="代码"><el-input v-model="transaction.asset_code" /></el-form-item>
        <el-form-item label="交易类型">
          <el-select v-model="transaction.trade_type" class="type-select">
            <el-option label="买入" value="buy" />
            <el-option label="卖出" value="sell" />
            <el-option v-if="transaction.asset_type === 'fund'" label="申购" value="subscription" />
            <el-option v-if="transaction.asset_type === 'fund'" label="赎回" value="redemption" />
          </el-select>
        </el-form-item>
        <el-form-item label="交易日期"><el-date-picker v-model="transaction.trade_date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="成交金额"><el-input-number v-model="transaction.amount" :min="0" /></el-form-item>
        <el-form-item :label="priceLabel"><el-input-number v-model="transaction.nav" :min="0" :precision="4" /></el-form-item>
        <el-form-item label="手续费"><el-input-number v-model="transaction.fee" :min="0" /></el-form-item>
        <el-form-item><el-button type="primary" :disabled="!transaction.asset_code" @click="addTransaction">保存并自动汇总</el-button></el-form-item>
        <el-form-item v-if="transaction.asset_type !== 'fund'"><el-button @click="syncAsset">同步股票/ETF 行情</el-button></el-form-item>
      </el-form>
      <p class="muted">基金使用净值，股票和 ETF 使用成交价；卖出记录会按当前平均成本重算剩余持仓。</p>
    </div>

    <div class="section metric-grid">
      <MetricCard
        label="当前市值"
        :value="overview && !overview.is_complete ? money(overview.known_value) : money(overview?.total_value)"
        :hint="overview && !overview.is_complete ? '估值不完整（已知部分）' : ''"
      />
      <MetricCard label="投入成本" :value="money(overview?.total_cost)" />
      <MetricCard
        label="收益金额"
        :value="money(overview?.profit_amount)"
        :hint="overview && overview.profit_amount === null && overview.missing_cost_assets.length ? '缺少成本信息' : ''"
      />
      <MetricCard label="收益率" :value="pct(overview?.profit_rate)" />
    </div>
    <el-alert
      v-if="valuationWarning"
      class="section alert-item"
      type="warning"
      :closable="false"
      show-icon
      title="组合估值不完整，整体盈亏暂不可用"
      :description="valuationWarning"
    />

    <div class="section panel">
      <h2 class="section-title">账户收益（现金 + 持仓）</h2>
      <div class="metric-grid">
        <MetricCard
          label="账户总资产"
          :value="money(account?.total_assets ?? account?.known_total_assets)"
          :hint="account && !account.is_complete ? '估值不完整（已知部分）' : ''"
        />
        <MetricCard label="现金余额" :value="money(account?.cash_balance)" />
        <MetricCard label="净投入" :value="money(account?.net_invested)" :hint="`含期初投入 ${money(account?.initial_investment)}`" />
        <MetricCard label="累计盈亏" :value="money(account?.cumulative_pnl)" />
        <MetricCard label="账户收益率" :value="pct(account?.return_rate)" hint="累计盈亏 / 净投入，含出入金时点影响" />
        <MetricCard label="时间加权收益率 (TWR)" :value="pct(account?.returns?.twr)" :hint="twrHint" />
        <MetricCard label="资金加权收益率 (XIRR)" :value="pct(account?.returns?.xirr)" :hint="xirrHint" />
        <MetricCard label="已实现盈亏" :value="money(account?.realized_pnl_total)" />
        <MetricCard label="未实现盈亏" :value="money(account?.unrealized_pnl_total)" />
        <MetricCard label="其他收益" :value="money(account?.other_income_total)" hint="分红 / 利息 / 费用 / 红利再投" />
      </div>
      <el-alert
        v-if="reconciliationWarning"
        class="alert-item"
        type="warning"
        :closable="false"
        show-icon
        :title="`账户恒等式核对偏差：${money(account?.reconciliation_difference)}`"
        description="累计盈亏 ≠ 已实现 + 未实现 + 其他收益，请检查流水或现金事件。"
      />
      <el-alert
        v-for="note in account?.notes || []"
        :key="note"
        class="alert-item"
        type="info"
        :closable="false"
        :title="note"
      />
      <el-radio-group v-if="hasBenchmarkSeries" v-model="performanceMode" size="small" class="chart-mode">
        <el-radio-button value="assets">资产与净投入</el-radio-button>
        <el-radio-button value="returns">累计收益率对比</el-radio-button>
      </el-radio-group>
      <div v-if="performance?.points.length" class="performance-chart"><ChartBox :option="performanceOption" /></div>
      <p v-if="performance" class="muted">
        {{ performance.label }}（{{ performance.coverage.start_date }} ~ {{ performance.coverage.end_date }}，
        共 {{ performance.coverage.points }} 个点{{ performance.is_complete ? "" : "；部分日期按成本估值" }}）
      </p>
      <template v-if="benchmark">
        <h3 class="section-title">基准对比 · {{ benchmark.index_name }}</h3>
        <el-alert
          v-if="benchmark.status !== 'ok'"
          class="alert-item"
          type="info"
          :closable="false"
          show-icon
          :title="benchmark.notes[0] || '基准数据不足'"
          description="在市场概览页同步指数数据后即可对比；也可通过 BENCHMARK_INDEX_CODE 配置其他基准。"
        />
        <div v-else class="metric-grid">
          <MetricCard label="区间收益（账户）" :value="pct(benchmark.metrics.account_cumulative)" :hint="`基准 ${pct(benchmark.metrics.benchmark_cumulative)}`" />
          <MetricCard label="超额收益" :value="pct(benchmark.metrics.excess_return)" :hint="`${benchmark.coverage.aligned_days} 个共同交易日`" />
          <MetricCard label="年化收益（账户）" :value="pct(benchmark.metrics.account_annualized)" :hint="`基准 ${pct(benchmark.metrics.benchmark_annualized)}`" />
          <MetricCard label="最大回撤（账户）" :value="pct(benchmark.metrics.account_max_drawdown)" :hint="`基准 ${pct(benchmark.metrics.benchmark_max_drawdown)}`" />
          <MetricCard label="Beta" :value="num(benchmark.metrics.beta, 3)" hint="账户对基准的敏感度" />
          <MetricCard label="Alpha（年化）" :value="pct(benchmark.metrics.alpha)" hint="无风险利率按 0" />
          <MetricCard label="相关性" :value="num(benchmark.metrics.correlation, 3)" />
        </div>
      </template>
    </div>

    <div class="section panel">
      <h2 class="section-title">基金拟买入模拟</h2>
      <el-form :model="simulationForm" inline>
        <el-form-item label="基金代码"><el-input v-model="simulationForm.fund_code" /></el-form-item>
        <el-form-item label="拟买金额"><el-input-number v-model="simulationForm.amount" :min="0" /></el-form-item>
        <el-form-item><el-button type="primary" :disabled="!simulationForm.fund_code || simulationForm.amount <= 0" @click="simulateBuy">计算组合影响</el-button></el-form-item>
      </el-form>
      <template v-if="simulation">
        <div class="metric-grid simulation-grid">
          <MetricCard label="买入后总市值" :value="money(simulation.total_value_after)" :hint="`买入前 ${money(simulation.total_value_before)}`" />
          <MetricCard label="目标基金占比" :value="pct(simulation.target_weight_after)" :hint="`买入前 ${pct(simulation.target_weight_before)}`" />
          <MetricCard label="最大持仓占比" :value="pct(simulation.max_weight_after)" :hint="`买入前 ${pct(simulation.max_weight_before)}`" />
          <MetricCard label="最高相关性" :value="correlationText(simulation.max_correlation)" :hint="`平均 ${correlationText(simulation.avg_correlation)}`" />
        </div>
        <el-alert v-for="risk in simulation.risk_items" :key="risk.title" class="alert-item" :type="risk.level === 'medium' ? 'warning' : 'info'" :closable="false" :title="risk.title" :description="risk.description" />
      </template>
    </div>

    <div class="section panel">
      <h2 class="section-title">组合诊断</h2>
      <div class="metric-grid">
        <MetricCard label="持仓数量" :value="diagnosis?.summary.position_count ?? 0" />
        <MetricCard label="最大持仓占比" :value="pct(diagnosis?.summary.max_weight)" />
        <MetricCard
          label="近 1 月回撤（当前持仓模拟）"
          :value="pct(diagnosis?.summary.drawdown_1m)"
          :hint="diagnosis?.summary.drawdown_basis?.window || ''"
        />
        <MetricCard label="组合收益率" :value="pct(diagnosis?.summary.profit_rate)" />
      </div>
      <el-alert v-for="risk in diagnosis?.risk_items || []" :key="risk.title" class="alert-item" :type="risk.level === 'medium' ? 'warning' : 'info'" :closable="false" :title="risk.title" :description="risk.description" />
      <p class="muted">{{ diagnosis?.observation }}</p>
    </div>

    <div class="section two-col">
      <div class="panel">
        <h2 class="section-title">统一持仓列表</h2>
        <el-table :data="positionRows" border stripe>
          <el-table-column prop="asset_type_label" label="类型" width="85" />
          <el-table-column prop="asset_code" label="代码" width="110" />
          <el-table-column prop="asset_name" label="名称" min-width="140" />
          <el-table-column prop="holding_share" label="持有数量" />
          <el-table-column prop="latest_price" label="最新价格/净值" />
          <el-table-column label="行情日期">
            <template #default="{ row }">
              <el-tag v-if="row.missing_reason" type="warning" size="small">缺失</el-tag>
              <span v-else>{{ dateText(row.price_date) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="current_value" label="当前市值" />
          <el-table-column label="收益率"><template #default="{ row }">{{ pct(row.profit_rate) }}</template></el-table-column>
          <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" @click="deletePosition(row.id)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
      <div class="panel"><h2 class="section-title">持仓占比</h2><ChartBox :option="pieOption" /></div>
    </div>

    <div class="section panel">
      <el-tabs v-model="ledgerTab">
        <el-tab-pane label="交易记录" name="transactions">
          <el-table :data="transactionRows" border stripe>
            <el-table-column prop="asset_type_label" label="类型" width="85" />
            <el-table-column prop="asset_code" label="代码" width="110" />
            <el-table-column prop="asset_name" label="名称" min-width="140" />
            <el-table-column prop="trade_type_label" label="交易" width="80" />
            <el-table-column prop="trade_date" label="交易日期" />
            <el-table-column prop="amount" label="成交金额" />
            <el-table-column prop="nav" label="成交价格/净值" />
            <el-table-column prop="share" label="数量" />
            <el-table-column label="已实现盈亏"><template #default="{ row }">{{ row.realized_pnl === null || row.realized_pnl === undefined ? "—" : money(row.realized_pnl) }}</template></el-table-column>
            <el-table-column label="操作" width="150"><template #default="{ row }"><el-button link type="danger" @click="deleteTransaction(row.id)">删除并重新汇总</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="现金与事件" name="cash">
          <el-form :model="cashForm" inline>
            <el-form-item label="类型">
              <el-select v-model="cashForm.event_type" class="type-select-wide">
                <el-option v-for="(label, value) in CASH_EVENT_LABEL" :key="value" :label="label" :value="value" />
              </el-select>
            </el-form-item>
            <el-form-item label="日期"><el-date-picker v-model="cashForm.event_date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="金额"><el-input-number v-model="cashForm.amount" :min="0" /></el-form-item>
            <el-form-item label="备注"><el-input v-model="cashForm.note" /></el-form-item>
            <el-form-item><el-button type="primary" :disabled="!cashForm.amount" @click="addCashEvent">添加</el-button></el-form-item>
          </el-form>
          <p class="muted">入金/出金/分红/利息/费用/调整按金额符号自动规范；期初现金只能设置一次。</p>
          <el-table :data="cashRows" border stripe>
            <el-table-column prop="event_date" label="日期" width="120" />
            <el-table-column prop="event_type_label" label="类型" width="100" />
            <el-table-column label="金额"><template #default="{ row }">{{ money(row.amount) }}</template></el-table-column>
            <el-table-column prop="note" label="备注" min-width="180" />
            <el-table-column prop="source" label="来源" width="120" />
            <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="danger" @click="removeCashEvent(row.id)">删除</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="导入批次" name="imports">
          <el-table :data="importBatches" border stripe>
            <el-table-column prop="id" label="批次" width="70" />
            <el-table-column label="来源" width="150"><template #default="{ row }">{{ SOURCE_KIND_LABEL[row.source_kind] || row.source_kind }}</template></el-table-column>
            <el-table-column prop="file_name" label="文件" min-width="160" />
            <el-table-column label="状态" width="100"><template #default="{ row }">{{ IMPORT_STATUS_LABEL[row.status] || row.status }}</template></el-table-column>
            <el-table-column label="结果" min-width="220"><template #default="{ row }">导入 {{ row.imported_count }} · 重复 {{ row.duplicate_count }} · 跳过 {{ row.skipped_count }} · 错误 {{ row.error_count }}</template></el-table-column>
            <el-table-column label="时间" min-width="160"><template #default="{ row }">{{ (row.rolled_back_at || row.committed_at || row.created_at || "").slice(0, 19) }}</template></el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'committed' || row.status === 'partial'"
                  link
                  type="danger"
                  :loading="rollingBackId === row.id"
                  @click="rollbackImport(row)"
                >整批回滚</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
    <el-dialog v-model="screenshotDialogOpen" title="核对持仓识别结果" width="min(1100px, 96vw)" destroy-on-close>
      <el-alert type="warning" :closable="false" show-icon title="请逐行核对后再导入" description="识别不清的字段会留空。已有交易流水的资产会被自动跳过，不会覆盖交易账本。" />
      <el-form class="import-date" inline>
        <el-form-item label="截图日期"><el-date-picker v-model="screenshotAsOfDate" value-format="YYYY-MM-DD" /></el-form-item>
      </el-form>
      <el-table :data="screenshotDrafts" border max-height="440">
        <el-table-column label="类型" width="110"><template #default="{ row }"><el-select v-model="row.asset_type"><el-option label="基金" value="fund" /><el-option label="股票" value="stock" /><el-option label="ETF" value="etf" /></el-select></template></el-table-column>
        <el-table-column label="代码" width="120"><template #default="{ row }"><el-input v-model="row.asset_code" /></template></el-table-column>
        <el-table-column label="名称" min-width="140"><template #default="{ row }"><el-input v-model="row.asset_name" /></template></el-table-column>
        <el-table-column label="持有数量" width="150"><template #default="{ row }"><el-input-number v-model="row.holding_share" :min="0" controls-position="right" /></template></el-table-column>
        <el-table-column label="成本价" width="130"><template #default="{ row }"><el-input-number v-model="row.cost_price" :min="0" :precision="4" controls-position="right" /></template></el-table-column>
        <el-table-column label="现价/净值" width="140"><template #default="{ row }"><el-input-number v-model="row.current_price" :min="0" :precision="4" controls-position="right" /></template></el-table-column>
        <el-table-column label="市值" width="140"><template #default="{ row }"><el-input-number v-model="row.market_value" :min="0" controls-position="right" /></template></el-table-column>
        <el-table-column label="操作" width="70"><template #default="{ $index }"><el-button link type="danger" @click="screenshotDrafts.splice($index, 1)">移除</el-button></template></el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="screenshotDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="importingScreenshot" :disabled="!screenshotDrafts.length" @click="importHoldingScreenshot">确认导入 {{ screenshotDrafts.length }} 项</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="csvDialogOpen" title="核对 CSV 导入内容" width="min(1200px, 96vw)" destroy-on-close>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        :title="`识别结果：${csvPreview?.detected.label || '未识别出画像'}（编码 ${csvPreview?.encoding || '-'}，分隔符 ${csvSeparatorText}）`"
        description="列映射自动识别；如字段对不上，可在后续版本用映射覆盖重新预览。标“疑似重复”的行默认跳过，勾选后强制导入。"
      />
      <el-alert
        v-for="warning in csvPreview?.warnings || []"
        :key="warning"
        class="alert-item"
        type="warning"
        :closable="false"
        :title="warning"
      />
      <div class="toolbar import-toolbar">
        <span class="muted">
          共 {{ csvPreview?.counts.total ?? 0 }} 行：可导入 {{ csvPreview?.counts.importable ?? 0 }} · 重复
          {{ csvPreview?.counts.duplicate ?? 0 }} · 疑似重复 {{ csvPreview?.counts.suspect ?? 0 }} · 忽略
          {{ csvPreview?.counts.ignored ?? 0 }} · 错误 {{ csvPreview?.counts.error ?? 0 }}
        </span>
      </div>
      <el-table :data="csvRows" border max-height="440">
        <el-table-column label="行" width="60" prop="row_index" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'error'" type="danger" effect="plain">错误</el-tag>
            <el-tag v-else-if="row.status === 'duplicate'" type="info" effect="plain">重复跳过</el-tag>
            <el-tag v-else-if="row.status === 'suspect'" type="warning" effect="plain">疑似重复</el-tag>
            <el-tag v-else-if="row.target === 'ignore'" type="info" effect="plain">忽略</el-tag>
            <el-tag v-else type="success" effect="plain">可导入</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="内容" min-width="320">
          <template #default="{ row }">{{ rowSummary(row) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="220">
          <template #default="{ row }">{{ row.reason || (row.warnings || []).join("；") }}</template>
        </el-table-column>
        <el-table-column label="强制导入" width="100">
          <template #default="{ row }">
            <el-checkbox v-if="row.status === 'suspect'" v-model="row.force_import" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="csvDialogOpen = false">取消</el-button>
        <el-button type="primary" :loading="committingImport" :disabled="!csvImportableCount" @click="commitCsvImport">
          确认导入 {{ csvImportableCount }} 行
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importResultDialogOpen" title="导入结果与持仓核对" width="min(900px, 96vw)">
      <p v-if="importResult" class="muted">
        导入 {{ importResult.counts.imported }} 行 · 重复跳过 {{ importResult.counts.duplicate }} · 忽略
        {{ importResult.counts.skipped }} · 错误 {{ importResult.counts.error }}
      </p>
      <el-table v-if="importResult?.position_effects.length" :data="importResult.position_effects" border stripe>
        <el-table-column prop="asset_code" label="资产" width="130" />
        <el-table-column label="持有份额"><template #default="{ row }">{{ row.holding_share ?? "—" }}</template></el-table-column>
        <el-table-column label="持仓成本"><template #default="{ row }">{{ money(row.holding_amount) }}</template></el-table-column>
        <el-table-column label="成本价"><template #default="{ row }">{{ row.cost_nav ?? "—" }}</template></el-table-column>
        <el-table-column label="已实现盈亏"><template #default="{ row }">{{ money(row.realized_pnl_total) }}</template></el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox, type UploadFile } from "element-plus";
import type { EChartsOption } from "echarts";
import { computed, onMounted, reactive, ref } from "vue";

import { api } from "../api/fundpilot";
import { dateText, money, num, pct } from "../api/format";
import type {
  AccountPerformance,
  AccountSummary,
  Asset,
  CashEvent,
  HoldingScreenshotDraft,
  ImportBatch,
  ImportCommitResult,
  ImportPreview,
  ImportPreviewRow,
  PortfolioBuySimulation,
  PortfolioDiagnosis,
  PortfolioOverview,
  WatchlistItem,
} from "../api/types";
import ChartBox from "../components/ChartBox.vue";
import MetricCard from "../components/MetricCard.vue";

const ASSET_LABEL: Record<string, string> = { fund: "基金", stock: "股票", etf: "ETF" };
const TRADE_LABEL: Record<string, string> = {
  buy: "买入",
  sell: "卖出",
  subscription: "申购",
  redemption: "赎回",
  opening: "期初",
  dividend_reinvest: "红利再投",
  split: "拆分",
};
const CASH_EVENT_LABEL: Record<string, string> = {
  deposit: "入金",
  withdraw: "出金",
  dividend: "现金分红",
  interest: "利息",
  fee: "费用",
  adjustment: "调整",
  opening_balance: "期初现金",
};
const IMPORT_STATUS_LABEL: Record<string, string> = {
  previewed: "待确认",
  committed: "已入账",
  partial: "部分入账",
  failed: "失败",
  rolled_back: "已回滚",
};
const SOURCE_KIND_LABEL: Record<string, string> = {
  citic_delivery: "中信成交明细",
  citic_statement: "中信资金流水",
  unknown: "未识别",
};
const loading = ref(false);
const overview = ref<PortfolioOverview | null>(null);
const diagnosis = ref<PortfolioDiagnosis | null>(null);
const simulation = ref<PortfolioBuySimulation | null>(null);
const transactions = ref<Array<Record<string, unknown>>>([]);
const watchlist = ref<WatchlistItem[]>([]);
const assets = ref<Asset[]>([]);
const recognizing = ref(false);
const importingScreenshot = ref(false);
const screenshotDialogOpen = ref(false);
const screenshotDrafts = ref<HoldingScreenshotDraft[]>([]);
const screenshotAsOfDate = ref(new Date().toISOString().slice(0, 10));
const transaction = reactive({ asset_type: "fund" as "fund" | "stock" | "etf", asset_code: "", trade_type: "buy", trade_date: "", amount: 0, nav: 0, fee: 0 });
const simulationForm = reactive({ fund_code: "", amount: 0 });
const priceLabel = computed(() => (transaction.asset_type === "fund" ? "成交净值" : "成交价格"));
const nameMap = computed(() => Object.fromEntries([
  ...watchlist.value.map((item) => [item.fund_code, item.fund_name || ""]),
  ...assets.value.map((item) => [item.asset_code, item.asset_name]),
]));
const positionRows = computed(() => (overview.value?.positions || []).map((item) => ({
  id: item.position.id,
  asset_type: item.asset_type || item.position.asset_type,
  asset_type_label: ASSET_LABEL[item.asset_type || item.position.asset_type] || item.asset_type,
  asset_code: item.asset_code || item.position.asset_code || item.position.fund_code,
  asset_name: item.asset_name || item.fund_name || "",
  holding_share: item.position.holding_share,
  latest_price: item.latest_price ?? item.latest_nav,
  price_date: item.price_date,
  missing_reason: item.missing_reason,
  current_value: item.current_value,
  profit_rate: item.profit_rate,
})));
const valuationWarning = computed(() => {
  const data = overview.value;
  if (!data || data.is_complete) return "";
  return data.missing_price_assets
    .map((item) => `${item.asset_name || item.asset_code}：${item.reason}`)
    .join("；");
});
const transactionRows = computed(() => transactions.value.map((item) => {
  const assetType = String(item.asset_type || "fund");
  const assetCode = String(item.asset_code || item.fund_code || "");
  return { ...item, asset_code: assetCode, asset_type_label: ASSET_LABEL[assetType] || assetType, asset_name: nameMap.value[assetCode] || "", trade_type_label: TRADE_LABEL[String(item.trade_type)] || item.trade_type };
}));
const pieOption = computed<EChartsOption>(() => ({
  tooltip: { trigger: "item" },
  series: [
    {
      type: "pie",
      radius: ["45%", "70%"],
      data: positionRows.value
        .filter((row) => row.current_value !== null && row.current_value !== undefined)
        .map((row) => ({ name: row.asset_name ? `${row.asset_name} (${row.asset_code})` : row.asset_code, value: row.current_value || 0 })),
    },
  ],
}));

// —— 账户收益与台账扩展 ——
const ledgerTab = ref("transactions");
const account = ref<AccountSummary | null>(null);
const performance = ref<AccountPerformance | null>(null);
const cashRows = ref<CashEvent[]>([]);
const cashForm = reactive({
  event_type: "deposit",
  event_date: new Date().toISOString().slice(0, 10),
  amount: 0,
  note: "",
});
const importBatches = ref<ImportBatch[]>([]);
const rollingBackId = ref<number | null>(null);
const csvDialogOpen = ref(false);
const previewingImport = ref(false);
const committingImport = ref(false);
const csvPreview = ref<ImportPreview | null>(null);
const csvRows = ref<ImportPreviewRow[]>([]);
const importResultDialogOpen = ref(false);
const importResult = ref<ImportCommitResult | null>(null);
const csvSeparatorText = computed(() => (csvPreview.value?.delimiter === "\t" ? "制表符" : csvPreview.value?.delimiter || "-"));
const csvImportableCount = computed(
  () => csvRows.value.filter((row) => row.status === "ok" || (row.status === "suspect" && row.force_import)).length
);
const reconciliationWarning = computed(() => {
  const diff = account.value?.reconciliation_difference;
  return diff !== null && diff !== undefined && Math.abs(Number(diff)) > 0.01;
});
const XIRR_STATUS_LABEL: Record<string, string> = {
  ok: "",
  insufficient_flows: "现金流不足，无法求解",
  all_same_sign: "现金流方向单一，无法求解",
  no_solution: "在合理区间内无解",
  zero_days: "起止日期相同，无法年化",
  short_window: "区间不足 30 天，年化不具参考意义",
};
const twrHint = computed(() => {
  const returns = account.value?.returns;
  if (!returns) return "";
  if (returns.twr_annualized !== null && returns.twr_annualized !== undefined) {
    return `年化 ${pct(returns.twr_annualized)}`;
  }
  return returns.notes?.[0] || returns.basis;
});
const xirrHint = computed(() => {
  const returns = account.value?.returns;
  if (!returns) return "";
  if (returns.xirr_status === "ok") return `已考虑 ${returns.flow_count} 笔外部现金流`;
  return XIRR_STATUS_LABEL[returns.xirr_status] || returns.xirr_status;
});
const performanceMode = ref<"assets" | "returns">("assets");
const benchmark = computed(() => performance.value?.benchmark || null);
const hasBenchmarkSeries = computed(() => (benchmark.value?.series.length || 0) > 1);
const performanceOption = computed<EChartsOption>(() => {
  const points = performance.value?.points || [];
  const twrIndex = performance.value?.returns?.twr_index || [];
  if (performanceMode.value === "returns" && hasBenchmarkSeries.value && benchmark.value) {
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["账户 TWR 累计", `${benchmark.value.index_name} 累计`] },
      grid: { left: 60, right: 24, top: 40, bottom: 40 },
      xAxis: { type: "category", data: benchmark.value.series.map((item) => item.point_date) },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: [
        {
          name: "账户 TWR 累计",
          type: "line",
          showSymbol: false,
          data: benchmark.value.series.map((item) =>
            item.account_index === null ? null : (Number(item.account_index) - 1) * 100
          ),
        },
        {
          name: `${benchmark.value.index_name} 累计`,
          type: "line",
          showSymbol: false,
          data: benchmark.value.series.map((item) =>
            item.benchmark_index === null ? null : (Number(item.benchmark_index) - 1) * 100
          ),
        },
      ],
    };
  }
  const hasTwr = twrIndex.length > 0 && twrIndex.length === points.length;
  return {
    tooltip: { trigger: "axis" },
    legend: { data: hasTwr ? ["账户总资产", "净投入", "TWR 累计"] : ["账户总资产", "净投入"] },
    grid: { left: 60, right: hasTwr ? 64 : 24, top: 40, bottom: 40 },
    xAxis: { type: "category", data: points.map((point) => point.point_date) },
    yAxis: [
      { type: "value" },
      { type: "value", axisLabel: { formatter: "{value}%" }, splitLine: { show: false } },
    ],
    series: [
      { name: "账户总资产", type: "line", showSymbol: false, data: points.map((point) => Number(point.total_assets)) },
      { name: "净投入", type: "line", showSymbol: false, data: points.map((point) => Number(point.net_invested)) },
      ...(hasTwr
        ? [{
            name: "TWR 累计",
            type: "line" as const,
            yAxisIndex: 1,
            showSymbol: false,
            data: twrIndex.map((item) => (item.index === null ? null : (Number(item.index) - 1) * 100)),
          }]
        : []),
    ],
  };
});

function rowSummary(row: ImportPreviewRow): string {
  const parsed = row.parsed;
  if (!parsed) return Object.values(row.raw || {}).join(" ");
  const label =
    row.target === "cash"
      ? CASH_EVENT_LABEL[String(parsed.event_type)] || String(parsed.event_type)
      : TRADE_LABEL[String(parsed.trade_type)] || String(parsed.trade_type);
  const amount = parsed.amount !== undefined && parsed.amount !== null ? ` ${parsed.amount}` : "";
  return `${parsed.trade_date || parsed.event_date || ""} ${parsed.asset_code || ""} ${label}${amount}`;
}

async function previewCsvImport(uploadFile: UploadFile) {
  if (!uploadFile.raw) return;
  previewingImport.value = true;
  try {
    const preview = await api.previewPortfolioImport(uploadFile.raw);
    csvPreview.value = preview;
    csvRows.value = preview.rows.map((row) => ({ ...row, force_import: false }));
    csvDialogOpen.value = true;
  } finally {
    previewingImport.value = false;
  }
}

async function commitCsvImport() {
  if (!csvPreview.value) return;
  committingImport.value = true;
  try {
    const rows = csvRows.value.filter((row) => row.status === "ok" || (row.status === "suspect" && row.force_import));
    importResult.value = await api.commitPortfolioImport(csvPreview.value.batch_id, rows);
    csvDialogOpen.value = false;
    importResultDialogOpen.value = true;
    ElMessage.success(`导入完成：新增 ${importResult.value.counts.imported} 行`);
    await load();
  } finally {
    committingImport.value = false;
  }
}

async function rollbackImport(batch: ImportBatch) {
  let reason = "";
  try {
    const prompt = await ElMessageBox.prompt(
      `将删除批次 #${batch.id} 入账的交易与现金事件，并按剩余流水重新汇总持仓，此操作不可撤销。可填写回滚原因：`,
      "整批回滚",
      {
        confirmButtonText: "确认回滚",
        cancelButtonText: "取消",
        type: "warning",
        inputPlaceholder: "例如：列映射选错了",
        inputValue: "",
      }
    );
    reason = prompt.value || "";
  } catch {
    return; // 用户取消
  }
  rollingBackId.value = batch.id;
  try {
    const result = await api.rollbackPortfolioImport(batch.id, reason || undefined);
    ElMessage.success(
      `已回滚：删除交易 ${result.counts.transactions} 条、现金事件 ${result.counts.cash_events} 条`
    );
    await load();
  } finally {
    rollingBackId.value = null;
  }
}

async function addCashEvent() {
  await api.addCashEvent({ ...cashForm });
  ElMessage.success("现金事件已添加");
  cashForm.amount = 0;
  cashForm.note = "";
  await load();
}

async function removeCashEvent(id: number) {
  await api.deleteCashEvent(id);
  ElMessage.success("已删除");
  await load();
}

async function loadLedgerExtras() {
  [cashRows.value, importBatches.value, account.value, performance.value] = await Promise.all([
    api.cashEvents(),
    api.portfolioImports(20),
    api.accountSummary(),
    api.accountPerformance(),
  ]);
}

async function load() {
  loading.value = true;
  try {
    [overview.value, transactions.value, diagnosis.value, watchlist.value, assets.value] = await Promise.all([
      api.portfolioOverview(), api.portfolioTransactions() as Promise<Array<Record<string, unknown>>>, api.portfolioDiagnosis() as Promise<PortfolioDiagnosis>, api.watchlist(), api.assets(),
    ]);
    await loadLedgerExtras();
  } finally { loading.value = false; }
}
async function addTransaction() {
  loading.value = true;
  try { await api.addTransaction({ ...transaction }); ElMessage.success("交易记录已保存"); await load(); } finally { loading.value = false; }
}
async function recognizeHoldingScreenshot(uploadFile: UploadFile) {
  if (!uploadFile.raw) return;
  recognizing.value = true;
  try {
    const result = await api.recognizeHoldingScreenshot(uploadFile.raw);
    screenshotDrafts.value = result.holdings.map((item) => ({ ...item }));
    screenshotDialogOpen.value = true;
    ElMessage.success(`已识别 ${result.holdings.length} 项持仓，请核对后确认导入`);
  } finally { recognizing.value = false; }
}
async function importHoldingScreenshot() {
  importingScreenshot.value = true;
  try {
    const result = await api.importHoldingScreenshot({ holdings: screenshotDrafts.value, as_of_date: screenshotAsOfDate.value });
    screenshotDialogOpen.value = false;
    const skipped = result.skipped.length ? `；跳过 ${result.skipped.length} 项已有交易流水的资产` : "";
    ElMessage.success(`导入完成：新增 ${result.created} 项，更新 ${result.updated} 项${skipped}`);
    await load();
  } finally { importingScreenshot.value = false; }
}
async function syncAsset() {
  loading.value = true;
  try { const result = await api.syncAsset(transaction.asset_code, transaction.asset_type as "stock" | "etf"); ElMessage.success(`已同步 ${result.synced_rows} 条行情`); await load(); } finally { loading.value = false; }
}
async function simulateBuy() { loading.value = true; try { simulation.value = await api.simulatePortfolioBuy({ ...simulationForm }); } finally { loading.value = false; } }
function correlationText(value?: number | null) { return value === null || value === undefined ? "暂无" : Number(value).toFixed(2); }
async function deleteTransaction(id: number) { await api.deleteTransaction(id); await load(); }
async function deletePosition(id: number) { await api.deletePosition(id); await load(); }
onMounted(load);
</script>

<style scoped>
.alert-item { margin-top: 10px; }
.simulation-grid { margin-top: 10px; }
.type-select { width: 110px; }
.type-select-wide { width: 150px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.screenshot-import { margin-bottom: 16px; }
.import-date { margin: 16px 0 4px; }
.import-toolbar { margin: 12px 0 8px; }
.performance-chart { margin-top: 12px; }
.chart-mode { margin-top: 12px; }
</style>
