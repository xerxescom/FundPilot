<template>
  <div class="skeleton-page">
    <div class="metric-grid">
      <div v-for="item in metricCount" :key="item" class="panel">
        <el-skeleton animated>
          <template #template>
            <el-skeleton-item variant="text" style="width: 42%" />
            <el-skeleton-item variant="h1" style="width: 68%; margin-top: 14px" />
            <el-skeleton-item variant="text" style="width: 52%; margin-top: 8px" />
          </template>
        </el-skeleton>
      </div>
    </div>
    <div class="section panel">
      <el-skeleton :rows="rows" animated />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    metricCount?: number;
    rows?: number;
  }>(),
  {
    metricCount: 4,
    rows: 6,
  },
);
</script>
