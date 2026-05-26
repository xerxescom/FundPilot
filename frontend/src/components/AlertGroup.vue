<template>
  <el-collapse-item :name="groupKey" :disabled="!items.length">
    <template #title>
      <span class="group-header">
        <span class="group-label">{{ groupLabel }}</span>
        <el-badge
          v-if="items.length"
          :value="items.length"
          :type="badgeType"
          class="group-badge"
        />
        <span v-else class="group-empty-hint">（已全部处理）</span>
      </span>
    </template>

    <div class="group-toolbar">
      <el-dropdown trigger="click" @command="onBatch">
        <el-button type="primary" size="small" :disabled="!items.length">
          一键处理全组
          <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="read">标为已读</el-dropdown-item>
            <el-dropdown-item command="handled">已处理</el-dropdown-item>
            <el-dropdown-item command="ignored">忽略</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <div v-for="alert in items" :key="alert.id" class="alert-row">
      <el-alert
        :type="levelType(alert.alert_level)"
        :closable="false"
        :title="alert.title || alert.alert_type"
        :description="alert.content || ''"
      >
        <template #default>
          <div class="alert-actions">
            <el-button size="small" @click="emit('single-update', alert.id, 'read')">
              标为已读
            </el-button>
            <el-button size="small" type="success" @click="emit('single-update', alert.id, 'handled')">
              已处理
            </el-button>
            <el-button size="small" @click="emit('single-update', alert.id, 'ignored')">
              忽略
            </el-button>
          </div>
        </template>
      </el-alert>
    </div>
  </el-collapse-item>
</template>

<script setup lang="ts">
import { ArrowDown } from "@element-plus/icons-vue";
import { computed } from "vue";

import type { Alert } from "../api/types";

const props = defineProps<{
  groupKey: string;
  groupLabel: string;
  items: Alert[];
}>();

const emit = defineEmits<{
  "batch-update": [ids: number[], status: string];
  "single-update": [id: number, status: string];
}>();

const badgeType = computed(() => {
  const hasHigh = props.items.some((a) => a.alert_level === "high");
  return hasHigh ? "danger" : "warning";
});

function levelType(level: string | null | undefined) {
  if (level === "high") return "error";
  if (level === "medium") return "warning";
  return "info";
}

function onBatch(status: string) {
  emit(
    "batch-update",
    props.items.map((a) => a.id),
    status
  );
}
</script>

<style scoped>
.group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 14px;
}

.group-badge {
  /* shrink the badge so it doesn't stretch the collapse title bar */
  line-height: 1;
}

.group-empty-hint {
  font-size: 12px;
  font-weight: 400;
  color: #94a3b8;
}

.group-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}

.alert-row + .alert-row {
  margin-top: 8px;
}

.alert-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  flex-wrap: wrap;
}
</style>
