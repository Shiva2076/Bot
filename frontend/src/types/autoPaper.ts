export interface AutoPaperSignal {
  id: number;
  generated_at: string;
  underlying: string;
  direction: string;
  contract_symbol: string | null;
  entry_premium: number | null;
  stop_loss: number | null;
  target: number | null;
  eligibility_status: string;
  execution_status: string;
  rejection_reasons: string[];
  trade_id: number | null;
}

export interface AutoPaperStatus {
  mode: string;
  enabled: boolean;
  config: {
    underlyings: string[];
    lots: number;
    entry_start: string;
    last_entry: string;
    square_off: string;
    max_entries_per_day: number;
  };
  session_phase: string;
  last_run_at: string | null;
  last_note: string | null;
  open_auto_positions: number;
  entries_today: number;
  signals_today: AutoPaperSignal[];
}
