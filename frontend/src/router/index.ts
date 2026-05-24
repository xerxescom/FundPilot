import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("../pages/HomeOverview.vue") },
  { path: "/data-health", name: "data-health", component: () => import("../pages/DataHealth.vue") },
  { path: "/market", name: "market", component: () => import("../pages/MarketOverview.vue") },
  { path: "/watchlist", name: "watchlist", component: () => import("../pages/WatchlistPage.vue") },
  { path: "/portfolio", name: "portfolio", component: () => import("../pages/PortfolioPage.vue") },
  { path: "/funds/:fundCode?", name: "fund-detail", component: () => import("../pages/FundDetail.vue") },
  { path: "/compare", name: "compare", component: () => import("../pages/FundCompare.vue") },
  { path: "/scores", name: "scores", component: () => import("../pages/ScoreRank.vue") },
  { path: "/score-trend", name: "score-trend", component: () => import("../pages/ScoreTrend.vue") },
  { path: "/correlation", name: "correlation", component: () => import("../pages/CorrelationAnalysis.vue") },
  { path: "/reports/daily", name: "daily-report", component: () => import("../pages/DailyReport.vue") },
  { path: "/reports/history", name: "report-history", component: () => import("../pages/ReportHistory.vue") },
  { path: "/tasks", name: "tasks", component: () => import("../pages/TaskCenter.vue") },
];

export default createRouter({
  history: createWebHistory(),
  routes,
});
