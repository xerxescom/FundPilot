<template>
  <div class="chart-skeleton">
    <el-skeleton animated>
      <template #template>
        <el-skeleton-item variant="text" style="width: 24%" />
        <el-skeleton-item variant="rect" class="chart-rect" />
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.chart-skeleton {
  padding: 8px 0;
}

.chart-rect {
  width: 100%;
  height: 360px;
  margin-top: 16px;
  border-radius: 8px;
}
</style>
