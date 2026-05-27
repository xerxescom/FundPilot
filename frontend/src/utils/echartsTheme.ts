/**
 * FundPilot ECharts 主题
 *
 * 与 CSS Design Token 体系保持一致：
 *  - 主色调：HSL(221, 83%, 53%)  → --color-accent-blue
 *  - 辅助色：sky / green / purple / amber / rose
 *  - 背景透明，由容器 panel 提供毛玻璃背景
 *
 * 在 ChartBox.vue 中通过 echarts.registerTheme / echarts.init(el, 'fundpilot')
 * 自动应用。
 */

import * as echarts from "echarts";

const PALETTE = [
  "hsl(221, 83%, 58%)",   // accent-blue
  "hsl(160, 84%, 39%)",   // accent-green
  "hsl(199, 89%, 48%)",   // accent-sky
  "hsl(258, 90%, 66%)",   // accent-purple
  "hsl(38,  92%, 50%)",   // accent-amber
  "hsl(348, 83%, 60%)",   // rose
  "hsl(186, 74%, 44%)",   // teal
  "hsl(270, 60%, 60%)",   // lavender
];

const THEME = {
  color: PALETTE,
  backgroundColor: "transparent",

  textStyle: {
    fontFamily: "Inter, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    color: "#64748b",
  },

  title: {
    textStyle: { color: "#111827", fontWeight: 700 },
    subtextStyle: { color: "#94a3b8" },
  },

  legend: {
    textStyle: { color: "#64748b" },
    icon: "roundRect",
    itemWidth: 12,
    itemHeight: 6,
  },

  tooltip: {
    backgroundColor: "rgba(255,255,255,0.92)",
    borderColor: "#e5e7eb",
    borderWidth: 1,
    extraCssText: "backdrop-filter: blur(8px); box-shadow: 0 4px 20px rgba(31,38,135,0.08); border-radius: 8px;",
    textStyle: { color: "#111827", fontSize: 13 },
  },

  axisLine: { lineStyle: { color: "#e5e7eb" } },

  axisTick: { lineStyle: { color: "#e5e7eb" } },

  axisLabel: { color: "#94a3b8", fontSize: 12 },

  splitLine: { lineStyle: { color: "#f1f5f9", type: "dashed" } },

  line: {
    smooth: true,
    symbolSize: 5,
    lineStyle: { width: 2.5 },
    emphasis: { lineStyle: { width: 3.5 } },
  },

  bar: {
    barMaxWidth: 40,
    itemStyle: { borderRadius: [4, 4, 0, 0] },
  },

  pie: {
    label: { color: "#334155" },
    itemStyle: {
      borderColor: "#ffffff",
      borderWidth: 2,
    },
  },
};

/** 注册主题（调用一次即可，在 main.ts 中引入此模块触发） */
echarts.registerTheme("fundpilot", THEME);

export const ECHARTS_THEME = "fundpilot";
