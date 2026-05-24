<template>
  <div class="panel">
    <div class="toolbar">
      <el-tag>{{ report.model_name || "未知模型" }}</el-tag>
      <el-tag :type="report.is_fallback ? 'warning' : 'success'">
        {{ report.is_fallback ? "规则兜底" : "模型生成" }}
      </el-tag>
      <span class="muted">{{ report.created_at }}</span>
    </div>
    <el-alert v-if="report.fallback_reason" type="warning" :closable="false" :title="report.fallback_reason" />
    <div class="report-content">{{ report.content }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Report } from "../api/types";

defineProps<{ report: Report }>();
</script>
