import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  source: string;
  children: ReactNode;
  /** Shown instead of the contribution when it fails. Nothing by default. */
  fallback?: ReactNode;
}

/** Keeps a failing contribution from taking down the page around it. */
export class ExtensionBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[extensions] ${this.props.source} failed to render`, error, info.componentStack);
  }

  render() {
    return this.state.failed ? (this.props.fallback ?? null) : this.props.children;
  }
}
