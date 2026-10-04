<template>
  <div class="error-state">
    <el-alert type="error" :closable="false" show-icon :title="title" :description="message" />
    <el-button class="retry" :loading="loading" @click="emit('retry')">{{ retryText }}</el-button>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string;
    message?: string;
    retryText?: string;
    loading?: boolean;
  }>(),
  { title: "加载失败", message: "", retryText: "重试", loading: false },
);

const emit = defineEmits<{ retry: [] }>();
</script>

<style scoped>
.error-state {
  padding: 8px 0;
}

.retry {
  margin-top: 12px;
}
</style>
