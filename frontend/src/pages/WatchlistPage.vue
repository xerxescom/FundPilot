<template>
  <div v-loading="loading || Boolean(syncing)" :element-loading-text="loadingText">
    <div class="panel">
      <h2 class="section-title">自选基金管理</h2>
      <el-form :model="form" inline>
        <el-form-item label="基金代码"><el-input v-model="form.fund_code" placeholder="000001" /></el-form-item>
        <el-form-item label="基金名称"><el-input v-model="form.fund_name" placeholder="可留空" /></el-form-item>
        <el-form-item label="行业/主题"><el-input v-model="form.industry" placeholder="例如：宽基" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" placeholder="长期观察" /></el-form-item>
        <el-form-item><el-button type="primary" :loading="loading" @click="add">添加自选</el-button></el-form-item>
      </el-form>
    </div>

    <div class="section panel">
      <el-skeleton v-if="loading && !rows.length" :rows="6" animated />
      <el-table v-else :data="rows" border stripe>
        <el-table-column prop="fund_code" label="基金代码" />
        <el-table-column prop="fund_name" label="基金名称" min-width="180" />
        <el-table-column prop="industry" label="行业/主题" />
        <el-table-column label="分析状态" min-width="150">
          <template #default="{ row }">
            <el-tag :type="row.analysis_status?.complete ? 'success' : 'warning'" effect="plain">
              {{ row.analysis_status?.status_label || "未分析" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最新净值">
          <template #default="{ row }">{{ row.analysis_status?.latest_nav_date || "暂无" }}</template>
        </el-table-column>
        <el-table-column label="评分">
          <template #default="{ row }">{{ scoreText(row.analysis_status?.latest_score) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" />
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row.fund_code)">详情</el-button>
            <el-button link type="primary" :disabled="Boolean(syncing)" @click="analyze(row.fund_code)">一键分析</el-button>
            <el-button link type="danger" :disabled="Boolean(syncing)" @click="remove(row.fund_code)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="section panel">
      <h2 class="section-title">同步操作</h2>
      <div class="toolbar">
        <el-input v-model="syncCode" placeholder="同步单只基金净值" style="max-width: 260px" />
        <el-button :loading="syncing === 'one'" :disabled="Boolean(syncing)" @click="syncOne">同步单只</el-button>
        <el-button type="primary" :loading="syncing === 'all'" :disabled="Boolean(syncing)" @click="syncAll">
          同步全部自选基金
        </el-button>
      </div>
      <el-skeleton v-if="syncing && !taskResult" :rows="4" animated />
      <TaskResultTable v-if="taskResult" :result="taskResult" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { api } from "../api/fundpilot";
import { scoreText } from "../api/format";
import type { AnalysisStatus, WatchlistItem } from "../api/types";
import TaskResultTable from "../components/TaskResultTable.vue";

type WatchlistRow = WatchlistItem & { analysis_status?: AnalysisStatus };

const loading = ref(false);
const router = useRouter();
const rows = ref<WatchlistRow[]>([]);
const syncCode = ref("");
const syncing = ref<false | "one" | "all" | "analyze">(false);
const taskResult = ref<unknown>();
const form = reactive({ fund_code: "", fund_name: "", industry: "", note: "" });
const loadingText = computed(() => {
  if (syncing.value === "all") return "正在同步全部自选基金净值，可能需要一点时间...";
  if (syncing.value === "one") return "正在同步单只基金净值...";
  if (syncing.value === "analyze") return "正在执行一键同步并分析...";
  return "正在更新自选基金...";
});

async function load() {
  loading.value = true;
  try {
    const items = await api.watchlist();
    rows.value = await Promise.all(
      items.map(async (item) => ({
        ...item,
        analysis_status: (await api.analysisStatus(item.fund_code).catch(() => undefined)) as AnalysisStatus | undefined,
      })),
    );
  } finally {
    loading.value = false;
  }
}

async function add() {
  if (!form.fund_code) return;
  loading.value = true;
  try {
    await api.addWatchlist({ ...form });
    ElMessage.success("已添加自选基金");
    Object.assign(form, { fund_code: "", fund_name: "", industry: "", note: "" });
    await load();
  } finally {
    loading.value = false;
  }
}

async function remove(code: string) {
  await api.removeWatchlist(code);
  ElMessage.success("已移除");
  await load();
}

function goDetail(code: string) {
  router.push(`/funds/${code}`);
}

async function analyze(code: string) {
  syncing.value = "analyze";
  taskResult.value = undefined;
  try {
    taskResult.value = await api.analyzeFund(code);
    ElMessage.success("同步分析完成");
    await load();
  } finally {
    syncing.value = false;
  }
}

async function syncOne() {
  if (!syncCode.value) return;
  syncing.value = "one";
  taskResult.value = undefined;
  try {
    taskResult.value = await api.syncFundNav(syncCode.value);
    await load();
  } finally {
    syncing.value = false;
  }
}

async function syncAll() {
  syncing.value = "all";
  taskResult.value = undefined;
  try {
    taskResult.value = await api.syncWatchlistNav();
    await load();
  } finally {
    syncing.value = false;
  }
}

onMounted(load);
</script>
