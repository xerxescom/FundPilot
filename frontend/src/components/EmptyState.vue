<template>
  <div class="empty-state">
    <el-empty :description="description">
      <el-button v-if="actionText" :loading="loading" @click="emit('retry')">{{ actionText }}</el-button>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    description?: string;
    actionText?: string;
    loading?: boolean;
  }>(),
  { description: "暂无数据", actionText: "", loading: false },
);

const emit = defineEmits<{ retry: [] }>();
</script>

<style scoped>
.empty-state {
  padding: 8px 0;
}
</style>
