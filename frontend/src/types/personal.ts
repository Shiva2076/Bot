export type TradeAction = 'BUY' | 'SELL';
export type TradeType = 'PAPER' | 'MANUAL';
export type TradeStatus = 'OPEN' | 'CLOSED';
export type OrderSource = 'SYSTEM_SIGNAL' | 'MANUAL_OVERRIDE' | 'LEGACY';

export interface PersonalTrade {
  id: number;
  symbol: string;
  action: TradeAction;
  trade_type: TradeType;
  status: TradeStatus;
  quantity: number;
  entry_price: number;
  entry_time: string;
  invested_amount: number;
  exit_price: number | null;
  exit_time: string | null;
  exit_reason: string | null;
  current_price: number | null;
  stop_loss: number | null;
  target_1: number | null;
  target_2: number | null;
  pnl: number;
  pnl_pct: number;
  order_source: OrderSource;
  override_reason: string | null;
  holding_days: number | null;
  confidence_at_entry: number | null;
  market_regime_at_entry: string | null;
  points_gained: number | null;
  tags: Record<string, any> | null;
}

export interface DailyTradeSummary {
  trade_date: string;
  entries: number;
  exits: number;
  wins: number;
  losses: number;
  realized_pnl: number;
  unrealized_pnl: number;
  trades: PersonalTrade[];
}

export interface PortfolioPnlSummary {
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  today_pnl: number;
  open_invested: number;
  open_positions: number;
  closed_trades: number;
  win_rate: number;
}

export interface PersonalHistory {
  as_of: string;
  summary: PortfolioPnlSummary;
  open_positions: PersonalTrade[];
  days: DailyTradeSummary[];
}