import { useEffect, useState } from 'react';
import { optionsAPI, tradingAPI } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { OptionUnderlying } from '../types/options';
import type { OptionPrediction } from '../types/prediction';
import type { TradeDecision } from '../types/tradeDecision';
import { apiErrorMessage } from '../utils/api-error';
import { decisionHeadline, decisionTone } from '../utils/tradeDecisionView';

const POLL_MS = 30000;
const labelStyle = { fontSize: '0.68rem', color: 'var(--text-muted)' } as const;

const INDEX_ROWS: {
  underlying: OptionUnderlying;
  label: string;
  tabSymbol: string;
  pollDelayMs: number;
}[] = [
  { underlying: 'NIFTY', label: 'NIFTY 50', tabSymbol: '^NSEI', pollDelayMs: 0 },
  { underlying: 'BANKNIFTY', label: 'BANK NIFTY', tabSymbol: '^NSEBANK', pollDelayMs: 2500 },
  { underlying: 'SENSEX', label: 'SENSEX', tabSymbol: '^BSESN', pollDelayMs: 5000 },
];

function formatExpiry(iso: string): string {
  if (!iso) return '--';
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function IndexSignalCell({
  underlying,
  label,
  tabSymbol,
  pollDelayMs,
  onSelectIndex,
  onPlaced,
}: {
  underlying: OptionUnderlying;
  label: string;
  tabSymbol: string;
  pollDelayMs: number;
  onSelectIndex: (symbol: string) => void;
  onPlaced: () => void;
}) {
  const [expiry, setExpiry] = useState('');
  const [expiryError, setExpiryError] = useState('');
  const [decision, setDecision] = useState<TradeDecision | null>(null);
  const [prediction, setPrediction] = useState<OptionPrediction | null>(null);
  const [pollError, setPollError] = useState('');
  const [lots, setLots] = useState(1);
  const [stopLoss, setStopLoss] = useState('');
  const [target, setTarget] = useState('');
  const [placing, setPlacing] = useState<'CALL' | 'PUT' | null>(null);
  const [placeMessage, setPlaceMessage] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const load = () => {
      optionsAPI.getExpiries(underlying)
        .then(res => {
          if (cancelled) return;
          const next = res.data.expiries[0] ?? '';
          setExpiry(next);
          setExpiryError(next ? '' : 'No expiry available');
        })
        .catch(err => {
          if (cancelled) return;
          const message = apiErrorMessage(err);
          setExpiryError(message);
          if (message.toLowerCase().includes('downloading')) {
            retryTimer = setTimeout(load, 5000);
          }
        });
    };
    load();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [underlying]);

  // Decision only (already runs prediction server-side). Fetch prediction once when
  // TRADE / contract appears — avoids 3× parallel cold predicts that starve Angel.
  usePolling(async () => {
    if (pollDelayMs > 0) await sleep(pollDelayMs);
    try {
      const decisionRes = await tradingAPI.getDecision(underlying, expiry);
      const next = decisionRes.data;
      setDecision(next);
      setPollError('');
      const needsContract =
        next.status === 'TRADE' || Boolean(next.contract_symbol);
      if (needsContract) {
        const predictionRes = await optionsAPI.getPrediction(underlying, expiry);
        setPrediction(predictionRes.data);
      } else {
        setPrediction(null);
      }
    } catch (err) {
      setPollError(apiErrorMessage(err));
    }
  }, POLL_MS, [underlying, expiry, pollDelayMs], expiry !== '');

  const contract = prediction?.contract ?? null;
  const contractKey = contract
    ? `${contract.quote.symbol}:${prediction?.generated_at ?? ''}`
    : '';

  useEffect(() => {
    if (!contract) return;
    setStopLoss(String(contract.levels.stop_loss));
    setTarget(String(contract.levels.target));
    setLots(1);
    setPlaceMessage(null);
  }, [contractKey]);

  const tradeReady = decision?.status === 'TRADE' && contract !== null;
  const canCall = tradeReady && prediction?.direction === 'CALL' && contract?.option_type === 'CE';
  const canPut = tradeReady && prediction?.direction === 'PUT' && contract?.option_type === 'PE';
  const tone = decision ? decisionTone(decision.status) : 'stop';
  const border = tone === 'go' ? 'var(--buy)' : 'var(--sell)';

  const place = async (side: 'CALL' | 'PUT') => {
    if (!contract || placing) return;
    setPlacing(side);
    setPlaceMessage(null);
    try {
      const res = await tradingAPI.placeOrder({
        symbol: contract.quote.symbol,
        action: 'BUY',
        lots: Math.max(1, lots),
        stop_loss: stopLoss ? Number(stopLoss) : null,
        target: target ? Number(target) : null,
        override_reason: null,
      });
      setPlaceMessage({
        text: `BUY ${res.data.quantity} @ ₹${res.data.entry_price.toFixed(2)} · ${res.data.order_source}`,
        ok: true,
      });
      onPlaced();
    } catch (err) {
      setPlaceMessage({ text: apiErrorMessage(err), ok: false });
    } finally {
      setPlacing(null);
    }
  };

  return (
    <div
      role="region"
      aria-label={`${label} signal`}
      className="card"
      style={{ flex: '1 1 220px', marginBottom: 0, borderLeft: `4px solid ${border}` }}
    >
      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => onSelectIndex(tabSymbol)}
        style={{ padding: 0, fontWeight: 800, fontSize: '0.95rem', marginBottom: 6 }}
      >
        {label}
      </button>

      {!decision && !expiryError ? (
        <div style={{ padding: '12px 0' }}><div className="spinner" /></div>
      ) : (
        <>
          <div style={{ fontWeight: 900, fontSize: '1.15rem', letterSpacing: '0.04em', color: border }}>
            {decision ? decisionHeadline(decision.status) : 'NO TRADE'}
          </div>
          <div style={{ ...labelStyle, marginTop: 4, fontWeight: 600, color: 'var(--text-secondary)' }}>
            {decision?.reason ?? expiryError ?? 'Loading…'}
          </div>
          <div style={{ ...labelStyle, marginTop: 4 }}>
            Exp {formatExpiry(expiry)}
            {contract ? ` · ${contract.quote.display_name}` : ''}
            {contract ? ` · ₹${contract.quote.ltp.toFixed(2)}` : ''}
          </div>
          {(pollError || expiryError) && decision && (
            <div style={{ ...labelStyle, marginTop: 4, color: 'var(--sell)' }}>
              {pollError || expiryError}
            </div>
          )}
        </>
      )}

      <div style={{ marginTop: 12 }}>
        <label style={labelStyle}>Lots (1 lot = {prediction?.lot_size ?? '--'} qty)</label>
        <input
          type="number"
          min={1}
          step={1}
          value={lots}
          disabled={!tradeReady}
          onChange={e => setLots(Math.max(1, Number(e.target.value) || 1))}
          style={{ width: '100%', marginTop: 4 }}
        />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10 }}>
        <div>
          <label style={labelStyle}>Stop Loss</label>
          <input
            type="number"
            step="0.05"
            min="0.05"
            value={stopLoss}
            disabled={!tradeReady}
            onChange={e => setStopLoss(e.target.value)}
            style={{ width: '100%', marginTop: 4 }}
          />
        </div>
        <div>
          <label style={labelStyle}>Target</label>
          <input
            type="number"
            step="0.05"
            min="0.05"
            value={target}
            disabled={!tradeReady}
            onChange={e => setTarget(e.target.value)}
            style={{ width: '100%', marginTop: 4 }}
          />
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
        <button
          type="button"
          className="btn btn-buy"
          disabled={!canCall || placing !== null}
          onClick={() => place('CALL')}
          style={{ padding: '10px 0', fontWeight: 700, justifyContent: 'center' }}
        >
          {placing === 'CALL' ? '…' : 'CALL'}
        </button>
        <button
          type="button"
          className="btn btn-sell"
          disabled={!canPut || placing !== null}
          onClick={() => place('PUT')}
          style={{ padding: '10px 0', fontWeight: 700, justifyContent: 'center' }}
        >
          {placing === 'PUT' ? '…' : 'PUT'}
        </button>
      </div>
      {placeMessage && (
        <div style={{
          fontSize: '0.72rem',
          marginTop: 8,
          color: placeMessage.ok ? 'var(--buy)' : 'var(--sell)',
        }}
        >
          {placeMessage.text}
        </div>
      )}
    </div>
  );
}

export default function IndexSignalBar({
  onSelectIndex,
  onPlaced,
}: {
  onSelectIndex: (symbol: string) => void;
  onPlaced: () => void;
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 12,
        marginBottom: 16,
        alignItems: 'stretch',
      }}
    >
      {INDEX_ROWS.map(row => (
        <IndexSignalCell
          key={row.underlying}
          underlying={row.underlying}
          label={row.label}
          tabSymbol={row.tabSymbol}
          pollDelayMs={row.pollDelayMs}
          onSelectIndex={onSelectIndex}
          onPlaced={onPlaced}
        />
      ))}
    </div>
  );
}
