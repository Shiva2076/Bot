import { useEffect, useRef, useState } from 'react';
import { optionsAPI } from '../api/client';
import { usePolling } from '../hooks/usePolling';
import type { OptionChain, OptionQuote, OptionUnderlying } from '../types/options';
import type { Instrument } from '../types/trading';
import { apiErrorMessage } from '../utils/api-error';

const CHAIN_POLL_MS = 8000;
const ITM_BACKGROUND = 'rgba(245, 158, 11, 0.06)';

const formatCompact = (value: number) =>
  value.toLocaleString('en-IN', { notation: 'compact', maximumFractionDigits: 1 });

const formatExpiry = (iso: string) =>
  new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' });

interface OptionChainTableProps {
  underlying: OptionUnderlying;
  expiry: string;
  onExpiryChange: (expiry: string) => void;
  selectedSymbol: string | null;
  onSelect: (instrument: Instrument) => void;
}

function QuoteCells({ quote, side, itm, selected, onBuy }: {
  quote: OptionQuote | null; side: 'CE' | 'PE'; itm: boolean; selected: boolean; onBuy: () => void;
}) {
  if (!quote) return <><td /><td /><td /><td /><td /></>;
  const up = quote.change >= 0;
  const background = itm ? ITM_BACKGROUND : undefined;
  const cells = [
    <td key="oi" className="mono" style={{ textAlign: 'right', color: 'var(--text-muted)', background }}>{formatCompact(quote.open_interest)}</td>,
    <td key="vol" className="mono" style={{ textAlign: 'right', color: 'var(--text-muted)', background }}>{formatCompact(quote.volume)}</td>,
    <td key="chg" className="mono" style={{ textAlign: 'right', color: up ? 'var(--buy)' : 'var(--sell)', background }}>{up ? '+' : ''}{quote.change_pct.toFixed(1)}%</td>,
    <td key="ltp" className="mono" style={{ textAlign: 'right', fontWeight: 700, background }}>{quote.ltp.toFixed(2)}</td>,
    <td key="buy" style={{ textAlign: 'center', background }}>
      <button className={`btn ${selected ? 'btn-primary' : 'btn-buy'}`} style={{ padding: '2px 10px', fontSize: '0.7rem' }} onClick={onBuy}>B</button>
    </td>,
  ];
  return <>{side === 'CE' ? cells : [...cells].reverse()}</>;
}

export default function OptionChainTable({ underlying, expiry, onExpiryChange, selectedSymbol, onSelect }: OptionChainTableProps) {
  const [expiries, setExpiries] = useState<string[]>([]);
  const [chain, setChain] = useState<OptionChain | null>(null);
  const [error, setError] = useState('');
  const atmRowRef = useRef<HTMLTableRowElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrolledFor = useRef('');

  useEffect(() => {
    setChain(null);
    setExpiries([]);
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const loadExpiries = () => {
      optionsAPI.getExpiries(underlying)
        .then(res => {
          if (cancelled) return;
          setExpiries(res.data.expiries);
          onExpiryChange(res.data.expiries[0] ?? '');
          setError('');
        })
        .catch(err => {
          if (cancelled) return;
          const message = apiErrorMessage(err);
          setError(message);
          if (message.toLowerCase().includes('downloading')) {
            retryTimer = setTimeout(loadExpiries, 5000);
          }
        });
    };
    loadExpiries();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [underlying]);

  usePolling(async () => {
    try {
      const res = await optionsAPI.getChain(underlying, expiry);
      setChain(res.data);
      setError('');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }, CHAIN_POLL_MS, [underlying, expiry], expiry !== '');

  useEffect(() => {
    const key = `${underlying}:${expiry}`;
    const container = containerRef.current;
    const row = atmRowRef.current;
    if (chain && chain.expiry === expiry && container && row && scrolledFor.current !== key) {
      container.scrollTop = row.offsetTop - container.clientHeight / 2;
      scrolledFor.current = key;
    }
  }, [chain, underlying, expiry]);

  const select = (quote: OptionQuote) => onSelect({
    symbol: quote.symbol,
    name: quote.display_name,
    kind: 'OPTION',
    lot_size: chain?.lot_size ?? 1,
    option_underlying: underlying,
  });

  return (
    <div className="card" style={{ marginTop: 20, padding: 0 }}>
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
        <div>
          <span className="card-title">Option Chain · {underlying}</span>
          {chain && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 10 }}>
              Spot <span className="mono" style={{ color: 'var(--text-primary)' }}>{chain.spot.toFixed(2)}</span> · Lot {chain.lot_size}
            </span>
          )}
        </div>
        <select value={expiry} onChange={e => onExpiryChange(e.target.value)}>
          {expiries.map(e => <option key={e} value={e}>{formatExpiry(e)}</option>)}
        </select>
      </div>
      {error && <div style={{ padding: '10px 20px', color: 'var(--sell)', fontSize: '0.78rem' }}>{error}</div>}
      {!chain ? (
        <div style={{ padding: 30, textAlign: 'center' }}><div className="spinner" /></div>
      ) : (
        <div ref={containerRef} className="table-container" style={{ maxHeight: 520, overflowY: 'auto', position: 'relative' }}>
          <table>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-card)', zIndex: 1 }}>
              <tr>
                <th colSpan={5} style={{ textAlign: 'center', color: 'var(--buy)' }}>CALLS</th>
                <th />
                <th colSpan={5} style={{ textAlign: 'center', color: 'var(--sell)' }}>PUTS</th>
              </tr>
              <tr>
                <th style={{ textAlign: 'right' }}>OI</th>
                <th style={{ textAlign: 'right' }}>Volume</th>
                <th style={{ textAlign: 'right' }}>Chg%</th>
                <th style={{ textAlign: 'right' }}>LTP</th>
                <th />
                <th style={{ textAlign: 'center' }}>Strike</th>
                <th />
                <th style={{ textAlign: 'right' }}>LTP</th>
                <th style={{ textAlign: 'right' }}>Chg%</th>
                <th style={{ textAlign: 'right' }}>Volume</th>
                <th style={{ textAlign: 'right' }}>OI</th>
              </tr>
            </thead>
            <tbody>
              {chain.rows.map(row => {
                const isAtm = row.strike === chain.atm_strike;
                return (
                  <tr key={row.strike} ref={isAtm ? atmRowRef : undefined}>
                    <QuoteCells quote={row.call} side="CE" itm={row.strike < chain.spot}
                      selected={row.call?.symbol === selectedSymbol} onBuy={() => row.call && select(row.call)} />
                    <td className="mono" style={{
                      textAlign: 'center', fontWeight: 700,
                      background: isAtm ? 'var(--accent)' : 'var(--bg-elevated)', color: isAtm ? '#fff' : 'var(--text-primary)',
                    }}>
                      {row.strike}
                    </td>
                    <QuoteCells quote={row.put} side="PE" itm={row.strike > chain.spot}
                      selected={row.put?.symbol === selectedSymbol} onBuy={() => row.put && select(row.put)} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
