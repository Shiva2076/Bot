import { useEffect, useMemo, useState } from 'react';
import { tradingAPI } from '../api/client';
import ChartStructurePanel from '../components/ChartStructurePanel';
import LiveChart from '../components/LiveChart';
import OptionChainTable from '../components/OptionChainTable';
import PredictionPanel, { type PredictionAddRequest } from '../components/PredictionPanel';
import PremarketPanel from '../components/PremarketPanel';
import { PnlText, Tag } from '../components/TradeBadges';
import { usePolling } from '../hooks/usePolling';
import type { PersonalTrade, TradeAction } from '../types/personal';
import type { ChartAnnotationCategory, ChartStructureFeatures } from '../types/prediction';
import type { CandleInterval, Instrument, Tick } from '../types/trading';
import { apiErrorMessage } from '../utils/api-error';
import { CHART_CATEGORIES, chartOverlayLines } from '../utils/chartStructureView';

const TICK_POLL_MS = 3000;
const POSITIONS_POLL_MS = 5000;
const CHART_STRUCTURE_POLL_MS = 120000;
const STOCKS_TAB = 'STOCKS';
const INTERVALS: CandleInterval[] = ['1m', '5m', '15m'];
type ChartVisibility = 'ON' | 'OFF';
const CHART_TABS: { id: ChartVisibility; label: string }[] = [
  { id: 'ON', label: 'Chart On' },
  { id: 'OFF', label: 'Chart Off' },
];

type PanelTab = 'ORDER' | 'PREDICTION';
const PANEL_TABS: { id: PanelTab; label: string }[] = [
  { id: 'ORDER', label: 'Place Order' },
  { id: 'PREDICTION', label: 'Prediction' },
];

interface OrderPrefill {
  lots: number;
  stopLoss: number;
  target: number;
  appliedAt: number;
}

const labelStyle = { fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: 6 } as const;
const formatInr = (value: number) => `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

function OrderPanel({ instrument, tick, onPlaced, onClear, prefill }: {
  instrument: Instrument;
  tick: Tick | null;
  onPlaced: () => void;
  onClear: (() => void) | null;
  prefill: OrderPrefill | null;
}) {
  const [lots, setLots] = useState(1);
  const [stopLoss, setStopLoss] = useState('');
  const [target, setTarget] = useState('');
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    setMessage(null);
    if (prefill) {
      setLots(prefill.lots);
      setStopLoss(String(prefill.stopLoss));
      setTarget(String(prefill.target));
      return;
    }
    setStopLoss('');
    setTarget('');
    setLots(1);
  }, [instrument.symbol, prefill?.appliedAt]);

  const isLotBased = instrument.kind !== 'STOCK';
  const isOption = instrument.kind === 'OPTION';
  const quantity = lots * instrument.lot_size;
  const approxValue = tick ? quantity * tick.ltp : 0;

  const place = async (action: TradeAction) => {
    setPlacing(true);
    setMessage(null);
    try {
      const res = await tradingAPI.placeOrder({
        symbol: instrument.symbol,
        action,
        lots,
        stop_loss: stopLoss ? Number(stopLoss) : null,
        target: target ? Number(target) : null,
      });
      setMessage({ text: `${action} ${res.data.quantity} @ ₹${res.data.entry_price.toFixed(2)} executed`, ok: true });
      setStopLoss(''); setTarget('');
      onPlaced();
    } catch (err) {
      setMessage({ text: apiErrorMessage(err), ok: false });
    } finally {
      setPlacing(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="card-title">Place Order · {instrument.name}</span>
        {onClear && (
          <button className="btn btn-ghost" style={{ padding: '2px 8px', fontSize: '0.7rem' }} onClick={onClear}>✕ Back to index</button>
        )}
      </div>
      {isOption && (
        <div style={{ marginBottom: 12, fontSize: '0.8rem' }}>
          Premium <span className="mono" style={{ fontWeight: 700, fontSize: '1.1rem' }}>{tick ? `₹${tick.ltp.toFixed(2)}` : '--'}</span>
          {tick && (
            <span className="mono" style={{ marginLeft: 8, color: tick.change >= 0 ? 'var(--buy)' : 'var(--sell)' }}>
              {tick.change >= 0 ? '+' : ''}{tick.change.toFixed(2)} ({tick.change_pct.toFixed(2)}%)
            </span>
          )}
        </div>
      )}
      <div style={{ marginBottom: 14 }}>
        <label style={labelStyle}>{isLotBased ? `Lots (1 lot = ${instrument.lot_size} qty)` : 'Quantity'}</label>
        <input type="number" min="1" step="1" value={lots} onChange={e => setLots(Math.max(1, Number(e.target.value)))} style={{ width: '100%' }} />
        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 6 }}>
          Qty {quantity} · {isOption ? 'Premium required' : 'Approx value'} <span className="mono" style={{ color: 'var(--text-primary)' }}>{tick ? formatInr(approxValue) : '--'}</span>
          {isLotBased && tick && <> · 1 lot ≈ <span className="mono">{formatInr(instrument.lot_size * tick.ltp)}</span></>}
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
        <div>
          <label style={labelStyle}>Stop Loss ({isOption ? 'premium' : 'price'})</label>
          <input type="number" step="0.05" min="0.05" value={stopLoss} onChange={e => setStopLoss(e.target.value)} style={{ width: '100%' }} />
        </div>
        <div>
          <label style={labelStyle}>Target ({isOption ? 'premium' : 'price'})</label>
          <input type="number" step="0.05" min="0.05" value={target} onChange={e => setTarget(e.target.value)} style={{ width: '100%' }} />
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: isOption ? '1fr' : '1fr 1fr', gap: 10 }}>
        <button className="btn btn-buy" disabled={placing || !tick} onClick={() => place('BUY')} style={{ padding: '12px 0', fontWeight: 700, justifyContent: 'center' }}>BUY</button>
        {!isOption && (
          <button className="btn btn-sell" disabled={placing || !tick} onClick={() => place('SELL')} style={{ padding: '12px 0', fontWeight: 700, justifyContent: 'center' }}>SELL</button>
        )}
      </div>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 8 }}>
        Market order at live price. Stop loss and target exit automatically.
      </div>
      {message && <div style={{ color: message.ok ? 'var(--buy)' : 'var(--sell)', fontSize: '0.78rem', marginTop: 10 }}>{message.text}</div>}
    </div>
  );
}

function PositionsTable({ positions, onExit }: { positions: PersonalTrade[]; onExit: (id: number) => void }) {
  const total = positions.reduce((sum, p) => sum + p.pnl, 0);
  return (
    <div className="card" style={{ marginTop: 20, padding: 0 }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between' }}>
        <span className="card-title">Open Positions ({positions.length})</span>
        <span>Live P&L: <PnlText value={total} /></span>
      </div>
      {positions.length === 0 ? (
        <div style={{ padding: 30, textAlign: 'center', color: 'var(--text-muted)' }}>No open positions.</div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Side</th>
                <th style={{ textAlign: 'right' }}>Qty</th>
                <th style={{ textAlign: 'right' }}>Avg</th>
                <th style={{ textAlign: 'right' }}>LTP</th>
                <th style={{ textAlign: 'right' }}>SL / Target</th>
                <th style={{ textAlign: 'right' }}>P&L</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => (
                <tr key={p.id}>
                  <td style={{ fontWeight: 600 }}>{p.symbol.replace('.NS', '')}</td>
                  <td><Tag label={p.action} color={p.action === 'BUY' ? 'var(--buy)' : 'var(--sell)'} /></td>
                  <td style={{ textAlign: 'right' }} className="mono">{p.quantity}</td>
                  <td style={{ textAlign: 'right' }} className="mono">₹{p.entry_price.toFixed(2)}</td>
                  <td style={{ textAlign: 'right' }} className="mono">{p.current_price !== null ? `₹${p.current_price.toFixed(2)}` : '--'}</td>
                  <td style={{ textAlign: 'right', fontSize: '0.75rem' }}>
                    <div style={{ color: 'var(--sell)' }}>SL: {p.stop_loss !== null ? `₹${p.stop_loss.toFixed(2)}` : '--'}</div>
                    <div style={{ color: 'var(--buy)' }}>T: {p.target_1 !== null ? `₹${p.target_1.toFixed(2)}` : '--'}</div>
                  </td>
                  <td style={{ textAlign: 'right' }}><PnlText value={p.pnl} pct={p.pnl_pct} /></td>
                  <td>
                    <button className="btn btn-ghost" style={{ padding: '4px 10px', fontSize: '0.72rem' }} onClick={() => onExit(p.id)}>Exit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Trade() {
  const [instruments, setInstruments] = useState<Instrument[]>([]);
  const [tab, setTab] = useState('^NSEI');
  const [stockSymbol, setStockSymbol] = useState('RELIANCE.NS');
  const [candleInterval, setCandleInterval] = useState<CandleInterval>('5m');
  const [tick, setTick] = useState<Tick | null>(null);
  const [selectedOption, setSelectedOption] = useState<Instrument | null>(null);
  const [orderPrefill, setOrderPrefill] = useState<OrderPrefill | null>(null);
  const [optionTick, setOptionTick] = useState<Tick | null>(null);
  const [expiry, setExpiry] = useState('');
  const [panelTab, setPanelTab] = useState<PanelTab>('ORDER');
  const [chartVisibility, setChartVisibility] = useState<ChartVisibility>('ON');
  const [chartStructure, setChartStructure] = useState<ChartStructureFeatures | null>(null);
  const [chartStructureError, setChartStructureError] = useState('');
  const [enabledCategories, setEnabledCategories] = useState<Set<ChartAnnotationCategory>>(
    () => new Set(CHART_CATEGORIES),
  );
  const [positions, setPositions] = useState<PersonalTrade[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    tradingAPI.getInstruments().then(res => setInstruments(res.data)).catch(err => setError(apiErrorMessage(err)));
  }, []);

  const symbol = tab === STOCKS_TAB ? stockSymbol : tab;
  const instrument = instruments.find(i => i.symbol === symbol);
  const indices = instruments.filter(i => i.kind === 'INDEX');
  const stocks = instruments.filter(i => i.kind === 'STOCK');
  const chartOn = chartVisibility === 'ON';
  const chartLevels = useMemo(
    () => chartOverlayLines(chartStructure, enabledCategories),
    [chartStructure, enabledCategories],
  );
  const chartProjections = useMemo(() => {
    if (!chartStructure?.data_ok || !enabledCategories.has('SCENARIOS')) return [];
    return chartStructure.projections ?? [];
  }, [chartStructure, enabledCategories]);

  const toggleCategory = (category: ChartAnnotationCategory) => {
    setEnabledCategories(prev => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  useEffect(() => {
    setTick(null);
    setSelectedOption(null);
    setOrderPrefill(null);
    setExpiry('');
    setPanelTab('ORDER');
    setChartStructure(null);
  }, [symbol]);
  useEffect(() => { setOptionTick(null); }, [selectedOption?.symbol]);
  useEffect(() => {
    if (!chartOn) setChartStructure(null);
  }, [chartOn]);

  usePolling(async () => {
    try {
      const res = await tradingAPI.getTick(symbol);
      setTick(res.data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, TICK_POLL_MS, [symbol]);

  usePolling(async () => {
    try {
      const res = await tradingAPI.getTick(selectedOption?.symbol ?? '');
      setOptionTick(res.data);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, TICK_POLL_MS, [selectedOption?.symbol], selectedOption !== null);

  usePolling(async () => {
    try {
      const res = await tradingAPI.getChartStructure(symbol);
      setChartStructure(res.data);
      setChartStructureError('');
    } catch (err) {
      setChartStructure(null);
      setChartStructureError(apiErrorMessage(err));
    }
  }, CHART_STRUCTURE_POLL_MS, [symbol, chartOn], chartOn && symbol !== '');

  const fetchPositions = async () => {
    try {
      const res = await tradingAPI.getPositions();
      setPositions(res.data.positions);
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  };
  usePolling(fetchPositions, POSITIONS_POLL_MS, []);

  const exitPosition = async (id: number) => {
    try {
      await tradingAPI.exitPosition(id);
      fetchPositions();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  };

  const selectOption = (option: Instrument, prefill: OrderPrefill | null = null) => {
    setSelectedOption(option);
    setOrderPrefill(prefill);
    setPanelTab('ORDER');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const addFromPrediction = (request: PredictionAddRequest) => {
    selectOption(
      {
        symbol: request.contract.quote.symbol,
        name: request.contract.quote.display_name,
        kind: 'OPTION',
        lot_size: request.lotSize,
        option_underlying: request.underlying,
      },
      {
        lots: 1,
        stopLoss: request.contract.levels.stop_loss,
        target: request.contract.levels.target,
        appliedAt: Date.now(),
      },
    );
  };

  const up = (tick?.change ?? 0) >= 0;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Trade</h1>
        <p className="page-subtitle">Live chart with instant market orders · Data via {tick?.provider ?? '--'}</p>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        {indices.map(i => (
          <button key={i.symbol} onClick={() => setTab(i.symbol)} className={`btn ${tab === i.symbol ? 'btn-primary' : 'btn-ghost'}`}>{i.name}</button>
        ))}
        <button onClick={() => setTab(STOCKS_TAB)} className={`btn ${tab === STOCKS_TAB ? 'btn-primary' : 'btn-ghost'}`}>NIFTY 50 Stocks</button>
        {tab === STOCKS_TAB && (
          <select value={stockSymbol} onChange={e => setStockSymbol(e.target.value)}>
            {stocks.map(s => <option key={s.symbol} value={s.symbol}>{s.name}</option>)}
          </select>
        )}
      </div>

      {error && <div className="card" style={{ marginBottom: 16, color: 'var(--sell)' }}>{error}</div>}

      <PremarketPanel compact />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'flex-start' }}>
        <div className="card" style={{ flex: '2 1 520px', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div>
              <div style={{ fontWeight: 700 }}>{instrument?.name ?? symbol}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <span className="mono" style={{ fontSize: '1.6rem', fontWeight: 800 }}>{tick ? tick.ltp.toLocaleString('en-IN', { minimumFractionDigits: 2 }) : '--'}</span>
                {tick && (
                  <span className="mono" style={{ color: up ? 'var(--buy)' : 'var(--sell)', fontWeight: 600 }}>
                    {up ? '+' : ''}{tick.change.toFixed(2)} ({up ? '+' : ''}{tick.change_pct.toFixed(2)}%)
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {INTERVALS.map(i => (
                <button key={i} onClick={() => setCandleInterval(i)} className={`btn ${candleInterval === i ? 'btn-primary' : 'btn-ghost'}`} style={{ padding: '4px 10px', fontSize: '0.72rem' }}>{i}</button>
              ))}
              {CHART_TABS.map(t => (
                <button
                  key={t.id}
                  onClick={() => setChartVisibility(t.id)}
                  className={`btn ${chartVisibility === t.id ? 'btn-primary' : 'btn-ghost'}`}
                  style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          {chartOn ? (
            <>
              <LiveChart
                symbol={symbol}
                interval={candleInterval}
                tick={tick}
                levels={chartLevels}
                projections={chartProjections}
              />
              {chartStructureError && (
                <div style={{ color: 'var(--sell)', fontSize: '0.75rem', marginTop: 8 }}>
                  Chart structure: {chartStructureError}
                </div>
              )}
              <ChartStructurePanel
                chart={chartStructure}
                enabledCategories={enabledCategories}
                onToggleCategory={toggleCategory}
              />
            </>
          ) : (
            <div style={{ padding: '48px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              Chart Off · switch to Chart On to show the time chart and structure levels
            </div>
          )}
        </div>

        {instrument && (
          <div style={{ flex: '1 1 280px' }}>
            {instrument.option_underlying && (
              <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                {PANEL_TABS.map(t => (
                  <button key={t.id} onClick={() => setPanelTab(t.id)} className={`btn ${panelTab === t.id ? 'btn-primary' : 'btn-ghost'}`} style={{ flex: 1, justifyContent: 'center' }}>{t.label}</button>
                ))}
              </div>
            )}
            {instrument.option_underlying && panelTab === 'PREDICTION'
              ? (
                <PredictionPanel
                  underlying={instrument.option_underlying}
                  expiry={expiry}
                  onAdd={addFromPrediction}
                />
              )
              : selectedOption
                ? (
                  <OrderPanel
                    instrument={selectedOption}
                    tick={optionTick}
                    onPlaced={fetchPositions}
                    onClear={() => { setSelectedOption(null); setOrderPrefill(null); }}
                    prefill={orderPrefill}
                  />
                )
                : (
                  <OrderPanel
                    instrument={instrument}
                    tick={tick}
                    onPlaced={fetchPositions}
                    onClear={null}
                    prefill={null}
                  />
                )}
          </div>
        )}
      </div>

      {instrument?.option_underlying && (
        <OptionChainTable
          underlying={instrument.option_underlying}
          expiry={expiry}
          onExpiryChange={setExpiry}
          selectedSymbol={selectedOption?.symbol ?? null}
          onSelect={selectOption}
        />
      )}

      <PositionsTable positions={positions} onExit={exitPosition} />
    </div>
  );
}
