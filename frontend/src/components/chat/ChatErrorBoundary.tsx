"use client";

import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ChatErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            padding: 48,
            textAlign: 'center',
          }}
        >
          <p style={{ fontSize: 16, fontWeight: 500, marginBottom: 8 }}>会话页面出错</p>
          <p style={{ fontSize: 13, color: '#9ca3af', marginBottom: 16 }}>
            {this.state.error?.message || '未知错误'}
          </p>
          <button
            onClick={() => {
              this.setState({ hasError: false, error: null });
              window.location.reload();
            }}
            style={{
              padding: '8px 20px',
              borderRadius: 8,
              border: 'none',
              background: '#3b82f6',
              color: '#fff',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            重新加载
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
