<template>
  <div v-loading="loading || syncing" :element-loading-text="syncing ? '正在同步基金净值，可能需要一点时间...' : '正在更新自选基金...'">
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
        <el-table-column prop="group_name" label="分组" />
        <el-table-column prop="note" label="备注" />
        <el-table-column label="状态"><template #default="{ row }">{{ row.is_active ? "启用" : "停用" }}</template></el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button link type="danger" :disabled="syncing" @click="remove(row.fund_code)">移除</el-button>
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
import { onMounted, reactive, ref } from "vue";

import { api } from "../api/fundpilot";
import type { WatchlistItem } from "../api/types";
import TaskResultTable from "../components/TaskResultTable.vue";

const loading = ref(false);
const rows = ref<WatchlistItem[]>([]);
const syncCode = ref("");
const syncing = ref<false | "one" | "all">(false);
const taskResult = ref<unknown>();
const form = reactive({ fund_code: "", fund_name: "", industry: "", note: "" });

async function load() {
  loading.value = true;
  try {
    rows.value = await api.watchlist();
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

async function syncOne() {
  if (!syncCode.value) return;
  syncing.value = "one";
  taskResult.value = undefined;
  try {
    taskResult.value = await api.syncFundNav(syncCode.value);
  } finally {
    syncing.value = false;
  }
}

async function syncAll() {
  syncing.value = "all";
  taskResult.value = undefined;
  try {
    taskResult.value = await api.syncWatchlistNav();
  } finally {
    syncing.value = false;
  }
}

onMounted(load);
</script>
