import { useEffect, useRef, useState } from 'react';
import type { DependencyList } from 'react';

function useTabVisible() {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || document.visibilityState === 'visible');
  useEffect(() => {
    const onVisibility = () => setVisible(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);
  return visible;
}

export function usePolling(callback: () => Promise<void>, intervalMs: number, deps: DependencyList, enabled = true) {
  const inFlight = useRef(false);
  const tabVisible = useTabVisible();
  useEffect(() => {
    if (!enabled || !tabVisible) return;
    const run = async () => {
      if (inFlight.current || document.visibilityState !== 'visible') return;
      inFlight.current = true;
      try { await callback(); } finally { inFlight.current = false; }
    };
    run();
    const timer = setInterval(run, intervalMs);
    return () => clearInterval(timer);
  }, [...deps, enabled, tabVisible]);
}
