<template>
  <el-table :data="rows" border stripe>
    <el-table-column v-for="column in columns" :key="column" :prop="column" :label="column" min-width="140" />
  </el-table>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ result: unknown }>();

function detailText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "无";
  if (Array.isArray(value)) return value.length ? value.map((item) => detailText(item)).join("；") : "无";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function statusText(value: unknown): string {
  if (value && typeof value === "object" && "status" in value) {
    return statusText((value as Record<string, unknown>).status);
  }
  if (typeof value !== "string") return "成功";
  if (value.startsWith("failed:") || value === "error") return "失败";
  if (value === "invalid" || value === "invalid_data") return "数据质量异常";
  if (value === "failed") return "失败";
  if (value === "skipped") return "已跳过";
  if (value === "queued") return "排队中";
  if (value === "running") return "执行中";
  if (value === "success") return "成功";
  return value;
}

const rows = computed(() => {
  if (Array.isArray(props.result)) {
    return props.result.map((value, index) => ({ 序号: index + 1, 结果: detailText(value) }));
  }
  if (props.result && typeof props.result === "object") {
    const result = props.result as Record<string, unknown>;
    if (Array.isArray(result.steps)) {
      const rowsFromSteps = result.steps.map((step, index) => {
        const stepRecord = step as Record<string, unknown>;
        return {
          序号: index + 1,
          步骤: detailText(stepRecord.label || stepRecord.key),
          状态: statusText(stepRecord.status),
          详情: detailText(stepRecord.result),
        };
      });
      const diagnostics = result.sync_diagnostics as Record<string, unknown> | undefined;
      if (diagnostics) {
        rowsFromSteps.push({
          序号: rowsFromSteps.length + 1,
          步骤: "同步诊断",
          状态: "成功",
          详情: `数据源：${detailText(diagnostics.source)}；同步行数：${detailText(diagnostics.synced_rows)}；质量问题：${detailText(
            (diagnostics.quality as Record<string, unknown> | undefined)?.issues
          )}`,
        });
      }
      return rowsFromSteps;
    }
    return Object.entries(result).map(([key, value]) => ({
      对象: key,
      结果: statusText(value),
      详情: detailText(value),
    }));
  }
  return [{ 结果: detailText(props.result) }];
});

const columns = computed(() => Object.keys(rows.value[0] || {}));
</script>
