// Catches render-time errors in the subtree it wraps so a single bad render
// shows a friendly message instead of unmounting the whole app (blank screen).
// In App it wraps <Routes> only, so the header and bottom nav stay usable.

import { Component } from 'react';
import { AlertTriangle } from 'lucide-react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    // Log only in development; production stays quiet.
    if (import.meta.env?.DEV) {
      console.error('Render error caught by ErrorBoundary:', error, info);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="card p-8 text-center space-y-4">
          <AlertTriangle className="w-10 h-10 mx-auto text-red-500" />
          <h2 className="text-xl font-bold">Something went wrong</h2>
          <p className="text-gray-600 dark:text-gray-300">
            This page hit an unexpected error. You can switch tabs below, or
            reload to start over.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary inline-block"
          >
            Reload
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
