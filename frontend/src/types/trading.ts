import type { OptionUnderlying } from './options';
import type { PersonalTrade, TradeAction } from './personal';

export type InstrumentKind = 'INDEX' | 'STOCK' | 'OPTION';
export type CandleInterval = '1m' | '5m' | '15m';

export interface Instrument {
  symbol: string;
  name: string;
  kind: InstrumentKind;
  lot_size: number;
  option_underlying: OptionUnderlying | null;
}

export interface Tick {
  symbol: string;
  ltp: number;
  prev_close: number;
  change: number;
  change_pct: number;
  timestamp: string;
  provider: string;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleSeries {
  symbol: string;
  interval: CandleInterval;
  provider: string;
  candles: Candle[];
}

export interface MarketOrderRequest {
  symbol: string;
  action: TradeAction;
  lots: number;
  stop_loss: number | null;
  target: number | null;
}

export interface OpenPositionsResponse {
  positions: PersonalTrade[];
}
