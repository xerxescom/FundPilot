<template>
  <el-table :data="rows" border stripe>
    <el-table-column v-for="column in columns" :key="column" :prop="column" :label="column" min-width="140" />
  </el-table>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ result: unknown }>();

const rows = computed(() => {
  if (Array.isArray(props.result)) {
    return props.result.map((value, index) => ({ 序号: index + 1, 结果: String(value) }));
  }
  if (props.result && typeof props.result === "object") {
    return Object.entries(props.result as Record<string, unknown>).map(([key, value]) => ({
      对象: key,
      结果: typeof value === "string" && value.startsWith("failed:") ? "失败" : "成功",
      详情: String(value),
    }));
  }
  return [{ 结果: String(props.result ?? "") }];
});

const columns = computed(() => Object.keys(rows.value[0] || {}));
</script>
