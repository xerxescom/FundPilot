<template>
  <div ref="chartRef" class="chart"></div>
</template>

<script setup lang="ts">
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ECHARTS_THEME } from "../utils/echartsTheme";

const props = defineProps<{ option: echarts.EChartsOption }>();
const chartRef = ref<HTMLDivElement | null>(null);

/**
 * chart 实例引用。在 onBeforeUnmount 中调用 dispose() 后立即置为 null，
 * 防止 SPA 路由切换时因 watch 回调竞态导致对已销毁实例的操作。
 */
let chart: echarts.ECharts | null = null;

/**
 * 标志位：组件是否已进入卸载阶段。
 * 用于阻断 watch 回调在卸载后再次触发 render()。
 */
let isUnmounting = false;

function render() {
  // 组件卸载过程中不再重建实例，避免内存泄漏
  if (isUnmounting || !chartRef.value) return;
  chart ||= echarts.init(chartRef.value, ECHARTS_THEME);
  chart.setOption(props.option, true);
}

function resize() {
  // dispose 后 chart 已置 null，可选链安全跳过
  chart?.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", resize);
});

// 深度监听 option 变化以更新图表；组件卸载后 render() 内部会提前返回
watch(() => props.option, render, { deep: true });

onBeforeUnmount(() => {
  isUnmounting = true;
  // 先移除全局事件监听，再销毁 ECharts 实例，最后置 null 释放引用
  window.removeEventListener("resize", resize);
  chart?.dispose();
  chart = null;
});
</script>
