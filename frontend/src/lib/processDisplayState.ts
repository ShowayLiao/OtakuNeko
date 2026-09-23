export function resolveProcessExpanded(
  expandable: boolean,
  hasRunning: boolean,
  userExpanded: boolean | null,
) {
  return expandable && (userExpanded ?? hasRunning);
}

export interface StepExpansionInput {
  hasBody: boolean;
  isAutoActive: boolean;
  userExpanded: boolean | null;
}

export function resolveStepExpanded({
  hasBody,
  isAutoActive,
  userExpanded,
}: StepExpansionInput) {
  if (!hasBody) return false;
  if (userExpanded != null) return userExpanded;
  return isAutoActive;
}

interface PendingToolCandidate {
  name?: string;
  sourceId?: string;
  status: string;
}

export function selectPendingTool<T extends PendingToolCandidate>(
  tools: T[],
  name: string,
  sourceId?: string,
) {
  const matches = tools.filter((tool) => tool.status === 'pending' && tool.name === name);
  if (sourceId) {
    return matches.findLast((tool) => tool.sourceId === sourceId);
  }
  return matches.length === 1 ? matches[0] : undefined;
}
