<template>
  <el-container class="app-shell">
    <el-aside class="sidebar" width="248px">
      <div class="brand">
        <div class="brand-title">FundPilot</div>
        <div class="brand-subtitle">本地基金投研助手</div>
      </div>
      <el-menu router :default-active="$route.path" class="nav-menu">
        <el-menu-item v-for="item in navItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="topbar">
        <div>
          <div class="page-title">{{ currentTitle }}</div>
          <div class="page-subtitle">Vue 主前端，本地基金投研工作台</div>
        </div>
        <el-tag type="success" effect="plain">FastAPI / Vue 3</el-tag>
      </el-header>
      <el-main class="content">
        <router-view v-slot="{ Component }">
          <Transition name="page" mode="out-in">
            <component :is="Component" :key="$route.path" />
          </Transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import {
  Bell,
  DataAnalysis,
  DataLine,
  Document,
  Files,
  Grid,
  HomeFilled,
  List,
  Money,
  Operation,
  TrendCharts,
  Wallet,
} from "@element-plus/icons-vue";
import { computed } from "vue";
import { useRoute } from "vue-router";

const navItems = [
  { path: "/", label: "今日驾驶舱", icon: HomeFilled },
  { path: "/data-health", label: "数据质量", icon: DataAnalysis },
  { path: "/market", label: "市场概览", icon: DataLine },
  { path: "/watchlist", label: "自选基金", icon: List },
  { path: "/portfolio", label: "我的持仓", icon: Wallet },
  { path: "/funds", label: "基金详情", icon: Files },
  { path: "/compare", label: "基金对比", icon: Grid },
  { path: "/scores", label: "评分排行", icon: TrendCharts },
  { path: "/score-trend", label: "评分趋势", icon: DataLine },
  { path: "/correlation", label: "相关性分析", icon: Operation },
  { path: "/reports/daily", label: "AI 简报", icon: Bell },
  { path: "/reports/history", label: "报告历史", icon: Document },
  { path: "/tasks", label: "任务中心", icon: Money },
];

const route = useRoute();
const currentTitle = computed(() => navItems.find((item) => item.path === route.path)?.label || "FundPilot");
</script>
