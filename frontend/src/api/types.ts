export type Nullable<T> = T | null;

export interface WatchlistItem {
  id: number;
  fund_code: string;
  fund_name?: Nullable<string>;
  industry?: Nullable<string>;
  group_name: string;
  note?: Nullable<string>;
  is_active: boolean;
  analysis_status?: AnalysisStatus;
}

export interface Score {
  fund_code: string;
  fund_name?: Nullable<string>;
  score_date?: Nullable<string>;
  total_score?: Nullable<number>;
  return_score?: Nullable<number>;
  drawdown_score?: Nullable<number>;
  volatility_score?: Nullable<number>;
  stability_score?: Nullable<number>;
  size_score?: Nullable<number>;
  trade_status_score?: Nullable<number>;
  rating?: Nullable<string>;
  reason?: Nullable<string>;
  confidence_score?: Nullable<number>;
  confidence_level?: Nullable<"high" | "medium" | "low">;
  buy_window_signal?: Nullable<"favorable" | "watch" | "wait_pullback" | "cautious" | "blocked">;
  buy_window_reason?: Nullable<string>;
  risk_flags?: string[];
  risk_flag_labels?: string[];
  market_signal?: Nullable<"supportive" | "neutral" | "weak">;
  market_reason?: Nullable<string>;
  market_pe_percentile?: Nullable<number>;
  peer_group?: Nullable<string>;
  peer_group_size?: Nullable<number>;
  peer_percentile?: Nullable<number>;
  peer_reason?: Nullable<string>;
  portfolio_fit_score?: Nullable<number>;
  portfolio_fit_level?: Nullable<"high" | "medium" | "low">;
  portfolio_fit_reason?: Nullable<string>;
  strategy?: Nullable<string>;
  strategy_name?: Nullable<string>;
  strategy_scenario?: Nullable<string>;
}

export interface ScoreStrategy {
  key: string;
  name: string;
  scenario: string;
}

export interface ScoreSignalSummary {
  total_scored: number;
  signal_counts: Record<string, number>;
  confidence_counts: Record<string, number>;
  top_risks: Array<{ label: string; count: number }>;
  favorable_count: number;
  watch_count: number;
  cautious_count: number;
}

export interface ScoreTrendRow {
  fund_code: string;
  score_date: string;
  total_score?: Nullable<number>;
  score_change?: Nullable<number>;
  trend_direction: "baseline" | "up" | "down" | "flat";
  rating_changed: boolean;
  previous_rating?: Nullable<string>;
  rating?: Nullable<string>;
  return_score?: Nullable<number>;
  drawdown_score?: Nullable<number>;
  volatility_score?: Nullable<number>;
  stability_score?: Nullable<number>;
  size_score?: Nullable<number>;
  trade_status_score?: Nullable<number>;
}

export interface Alert {
  id: number;
  alert_type: string;
  fund_code?: Nullable<string>;
  alert_level?: Nullable<string>;
  title?: Nullable<string>;
  content?: Nullable<string>;
  status: string;
  is_read: boolean;
  created_at: string;
}

export interface AnalysisStep {
  key: string;
  label: string;
  done: boolean;
}

export interface AnalysisStatus {
  fund_code: string;
  fund_name?: Nullable<string>;
  fund_type?: Nullable<string>;
  latest_nav_date?: Nullable<string>;
  latest_nav?: Nullable<number>;
  latest_indicator_date?: Nullable<string>;
  latest_score?: Nullable<number>;
  rating?: Nullable<string>;
  score_reason?: Nullable<string>;
  latest_report_at?: Nullable<string>;
  data_status: string;
  data_issues: string[];
  status: string;
  status_label: string;
  steps: AnalysisStep[];
  complete: boolean;
}

export interface SyncAttempt {
  source: string;
  attempt: number;
  status: string;
  row_count: number;
  issues: string[];
}

export interface NavQuality {
  valid: boolean;
  issues: string[];
  row_count: number;
  duplicate_count: number;
  missing_daily_return_count: number;
}

export interface SyncDiagnostics {
  fund_code: string;
  synced_rows: number;
  source: string;
  attempts: SyncAttempt[];
  quality: NavQuality;
  status?: string;
}

export interface AnalyzeWorkflowStep {
  key: string;
  label: string;
  status: string;
  result: unknown;
}

export interface AnalyzeResult {
  fund_code: string;
  steps: AnalyzeWorkflowStep[];
  sync_diagnostics?: SyncDiagnostics;
  status?: AnalysisStatus;
}

export interface DashboardTodo {
  key: string;
  title: string;
  description: string;
  action: string;
  route: string;
  level: "success" | "warning" | "info" | "danger";
}

export interface RiskItem {
  level: string;
  title: string;
  description: string;
}

export interface PortfolioDiagnosis {
  summary: {
    position_count: number;
    total_value?: Nullable<number>;
    profit_rate?: Nullable<number>;
    max_weight?: Nullable<number>;
    drawdown_1m?: Nullable<number>;
  };
  risk_items: RiskItem[];
  observation: string;
}

export interface Report {
  id: number;
  report_type: string;
  target_code?: Nullable<string>;
  title?: Nullable<string>;
  content: string;
  model_name?: Nullable<string>;
  is_fallback: boolean;
  fallback_reason?: Nullable<string>;
  input_snapshot?: Nullable<string>;
  created_at: string;
}

export interface MarketContext {
  index_code: string;
  index_name: string;
  trade_date?: Nullable<string>;
  close?: Nullable<number>;
  daily_return?: Nullable<number>;
  return_1m?: Nullable<number>;
  pe_ttm?: Nullable<number>;
  pe_percentile?: Nullable<number>;
  valuation_date?: Nullable<string>;
  source?: Nullable<string>;
}

export interface FundNav {
  fund_code: string;
  nav_date: string;
  unit_nav?: Nullable<number>;
  accumulated_nav?: Nullable<number>;
  daily_return?: Nullable<number>;
  source?: Nullable<string>;
}

export interface Indicator {
  fund_code: string;
  calc_date: string;
  return_1m?: Nullable<number>;
  return_3m?: Nullable<number>;
  return_6m?: Nullable<number>;
  return_1y?: Nullable<number>;
  max_drawdown_1y?: Nullable<number>;
  volatility_1y?: Nullable<number>;
  sharpe_1y?: Nullable<number>;
  win_rate_1y?: Nullable<number>;
}

export interface PortfolioOverview {
  total_value: number;
  total_cost?: Nullable<number>;
  profit_amount?: Nullable<number>;
  profit_rate?: Nullable<number>;
  max_weight?: Nullable<number>;
  drawdown_1m?: Nullable<number>;
  positions: Array<{
    position: {
      id: number;
      fund_code: string;
      holding_amount?: Nullable<number>;
      holding_share?: Nullable<number>;
      cost_nav?: Nullable<number>;
      buy_date?: Nullable<string>;
      note?: Nullable<string>;
    };
    latest_nav?: Nullable<number>;
    current_value?: Nullable<number>;
    profit_amount?: Nullable<number>;
    profit_rate?: Nullable<number>;
  }>;
}

export interface DataHealth {
  watchlist_count: number;
  latest_nav_date?: Nullable<string>;
  latest_available_trade_date?: Nullable<string>;
  stale_fund_count: number;
  failed_fund_count: number;
  pending_indicator_count: number;
  pending_score_count: number;
  pending_report_count: number;
  missing_daily_return_count: number;
  gap_count: number;
  duplicate_date_count: number;
  status_counts: Record<string, number>;
  funds: Array<Record<string, unknown>>;
}
