import { describe, expect, it } from 'vitest';

import { resolveChatSelection } from './chatDefaults';

describe('resolveChatSelection', () => {
  it('falls back to the first configured provider after server sessions are loaded', () => {
    const selection = resolveChatSelection(undefined, {
      openai: { enabled: true, apiKey: '' },
      deepseek: { enabled: true, apiKey: 'deepseek-key' },
    });

    expect(selection).toEqual({ model: 'deepseek-v4-flash', provider: 'deepseek' });
  });

  it('ignores a stale session provider when it no longer has credentials', () => {
    const selection = resolveChatSelection(
      { model: 'gpt-4o', provider: 'openai' },
      {
        openai: { enabled: true, apiKey: '' },
        ollama: { enabled: true, apiKey: 'ollama' },
      },
    );

    expect(selection).toEqual({ model: 'llama3:8b', provider: 'ollama' });
  });

  it('keeps the existing safe fallback when no provider is configured', () => {
    expect(resolveChatSelection(undefined, {})).toEqual({
      model: 'gpt-3.5-turbo',
      provider: 'openai',
    });
  });
});
