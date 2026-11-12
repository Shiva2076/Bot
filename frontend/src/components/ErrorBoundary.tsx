import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/** Keeps one failing page from blanking the whole app; resets when resetKey (the route) changes. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page render failed', error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card" style={{ color: 'var(--sell)' }}>
        <div className="card-title" style={{ marginBottom: 8 }}>This page failed to render</div>
        <div className="mono" style={{ fontSize: '0.8rem', marginBottom: 12 }}>{this.state.error.message}</div>
        <button className="btn btn-ghost" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
