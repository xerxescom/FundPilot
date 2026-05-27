<template>
  <div class="metric-card" :class="accent ? `metric-card--${accent}` : ''">
    <div class="metric-label">{{ label }}</div>
    <div class="metric-value">{{ value }}</div>
    <div v-if="hint" class="metric-hint">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  value: string | number;
  hint?: string | number | null;
  /**
   * 可选：顶部强调色线条语义
   * 'blue' | 'green' | 'sky' | 'purple' | 'amber'
   */
  accent?: "blue" | "green" | "sky" | "purple" | "amber";
}>();
</script>

<style scoped>
.metric-card {
  position: relative;
  min-height: 102px;
  padding: 14px 16px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--glass-shadow);
  overflow: hidden;
  transition:
    transform var(--dur-normal) var(--ease-smooth),
    box-shadow var(--dur-normal) var(--ease-smooth),
    border-color var(--dur-normal) var(--ease-smooth);
}

/* 顶部彩色渐变指示线 */
.metric-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  opacity: 0;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  transition: opacity var(--dur-normal) var(--ease-smooth);
}

/* accent 变体 */
.metric-card--blue::before  { background: linear-gradient(90deg, var(--color-accent-blue), var(--color-accent-sky)); opacity: 1; }
.metric-card--green::before { background: linear-gradient(90deg, var(--color-accent-green), hsl(160, 60%, 55%)); opacity: 1; }
.metric-card--sky::before   { background: linear-gradient(90deg, var(--color-accent-sky), var(--color-accent-blue)); opacity: 1; }
.metric-card--purple::before{ background: linear-gradient(90deg, var(--color-accent-purple), hsl(258, 60%, 80%)); opacity: 1; }
.metric-card--amber::before { background: linear-gradient(90deg, var(--color-accent-amber), hsl(38, 92%, 68%)); opacity: 1; }

/* Hover */
.metric-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--glass-shadow-hover);
  border-color: rgba(255, 255, 255, 0.75);
}

/* 数字进场动画 */
.metric-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 760;
  animation: metric-count-in var(--dur-normal) var(--ease-spring) both;
}

@keyframes metric-count-in {
  from {
    opacity: 0;
    transform: scale(0.88) translateY(4px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.metric-label {
  color: var(--color-muted);
  font-size: 13px;
}

.metric-hint {
  margin-top: 5px;
  color: var(--color-muted);
  font-size: 12px;
}
</style>
