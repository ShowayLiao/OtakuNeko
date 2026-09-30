import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import ProcessStepItem from '@/components/chat/ProcessStepItem';
import type { ProcessNode } from '@/stores/useChatStore';

describe('ProcessStepItem terminal invocation states', () => {
  it.each([
    ['denied', 'Denied'],
    ['cancelled', 'Cancelled'],
    ['timeout', 'Timed out'],
  ])('renders an explicit %s label', (status, label) => {
    const node = {
      id: `inv-${status}`,
      stepNumber: 1,
      type: 'tool_call',
      status,
      title: 'library.search',
      errorCode: status === 'timeout' ? 'timeout' : undefined,
    } as unknown as ProcessNode;

    render(
      <ProcessStepItem
        node={node}
        stepNumber={1}
        isDarkMode={false}
        autoExpanded={false}
      />,
    );

    expect(screen.getByText(label)).toBeDefined();
  });

  it('bounds tool output and marks it as untrusted external data', () => {
    const node = {
      id: 'inv-output',
      stepNumber: 1,
      type: 'tool_call',
      status: 'success',
      title: 'library.search',
      output: 'x'.repeat(5000),
    } as unknown as ProcessNode;

    const { container } = render(
      <ProcessStepItem
        node={node}
        stepNumber={1}
        isDarkMode={false}
        autoExpanded
      />,
    );

    expect(screen.getByText(/外部工具输出/)).toBeDefined();
    const output = container.querySelector('pre:last-of-type');
    expect(output?.textContent?.length).toBeLessThanOrEqual(4001);
  });

  it('bounds displayed invocation arguments', () => {
    const node = {
      id: 'inv-input',
      stepNumber: 1,
      type: 'tool_call',
      status: 'success',
      title: 'library.search',
      details: { query: 'x'.repeat(5000) },
    } as unknown as ProcessNode;

    const { container } = render(
      <ProcessStepItem
        node={node}
        stepNumber={1}
        isDarkMode={false}
        autoExpanded
      />,
    );

    const input = container.querySelector('pre');
    expect(input?.textContent?.length).toBeLessThanOrEqual(4001);
  });
});
