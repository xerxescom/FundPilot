<template>
  <el-table :data="rows" border stripe>
    <el-table-column
      v-for="column in columns"
      :key="column"
      :prop="column"
      :label="fieldLabel(column)"
      min-width="140"
      show-overflow-tooltip
    />
  </el-table>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { fieldLabel } from "../api/labels";

const props = defineProps<{ rows: Array<Record<string, unknown>> }>();
const columns = computed(() => Object.keys(props.rows[0] || {}));
</script>
