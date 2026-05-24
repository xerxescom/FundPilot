<template>
  <el-select v-model="model" filterable clearable placeholder="选择基金" style="min-width: 260px">
    <el-option
      v-for="item in items"
      :key="item.fund_code"
      :label="`${item.fund_code} ${item.fund_name || ''}`"
      :value="item.fund_code"
    />
  </el-select>
</template>

<script setup lang="ts">
import type { WatchlistItem } from "../api/types";

defineProps<{ items: WatchlistItem[] }>();
const model = defineModel<string | undefined>();
</script>
