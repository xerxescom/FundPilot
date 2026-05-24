export type Nullable<T> = T | null;

export interface WatchlistItem {
  id: number;
  fund_code: string;
  fund_name?: Nullable<string>;
  industry?: Nullable<string>;
  group_name: string;
  note?: Nullable<string>;
  is_active: boolean;
}

export interface Score {
  fund_code: string;
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
}

export interface Alert {
  id: number;
  alert_type: string;
  fund_code?: Nullable<string>;
  alert_level?: Nullable<string>;
  title?: Nullable<string>;
  content?: Nullable<string>;
  is_read: boolean;
  created_at: string;
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
  missing_daily_return_count: number;
  gap_count: number;
  duplicate_date_count: number;
  status_counts: Record<string, number>;
  funds: Array<Record<string, unknown>>;
}
