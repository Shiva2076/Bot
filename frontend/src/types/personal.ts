export type TradeAction = 'BUY' | 'SELL';
export type TradeType = 'PAPER' | 'MANUAL';
export type TradeStatus = 'OPEN' | 'CLOSED';

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
  pnl: number;
  pnl_pct: number;
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