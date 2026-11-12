import { useEffect, useState, type ReactNode } from 'react';
import { RouteActivityProvider } from '../hooks/routeActivity';

/**
 * Mounts children on first visit and keeps them alive when navigating away,
 * so Trade/Personal do not remount (no full spinner reload). Polling pauses
 * via RouteActivityProvider while hidden.
 */
export default function PersistentRoute({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  const [mounted, setMounted] = useState(active);

  useEffect(() => {
    if (active) setMounted(true);
  }, [active]);

  if (!mounted) return null;

  return (
    <div style={{ display: active ? 'block' : 'none' }} aria-hidden={!active}>
      <RouteActivityProvider active={active}>{children}</RouteActivityProvider>
    </div>
  );
}
