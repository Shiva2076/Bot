export function PnlText({ value, pct }: { value: number; pct?: number }) {
  const pos = value >= 0;
  return (
    <span style={{ color: pos ? 'var(--buy)' : 'var(--sell)', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
      {pos ? '+' : '-'}₹{Math.abs(value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
      {pct !== undefined && <span style={{ fontSize: '0.72rem', marginLeft: 4 }}>({pos ? '+' : ''}{pct.toFixed(2)}%)</span>}
    </span>
  );
}

export function Tag({ label, color }: { label: string; color: string }) {
  return (
    <span style={{ padding: '2px 8px', borderRadius: 12, fontSize: '0.65rem', fontWeight: 700, color, border: `1px solid ${color}` }}>
      {label}
    </span>
  );
}
