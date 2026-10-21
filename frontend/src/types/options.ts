export type OptionUnderlying = 'NIFTY' | 'BANKNIFTY';

export interface OptionQuote {
  symbol: string;
  display_name: string;
  ltp: number;
  change: number;
  change_pct: number;
  open_interest: number;
  volume: number;
  bid: number | null;
  ask: number | null;
  implied_volatility: number | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
}

export interface OptionChainRow {
  strike: number;
  call: OptionQuote | null;
  put: OptionQuote | null;
}

export interface OptionChain {
  underlying: OptionUnderlying;
  expiry: string;
  spot: number;
  atm_strike: number;
  lot_size: number;
  rows: OptionChainRow[];
}

export interface OptionExpiries {
  underlying: OptionUnderlying;
  expiries: string[];
}
