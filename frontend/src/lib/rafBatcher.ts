type FrameCallback = (callback: () => void) => number;

export interface RafBatcher {
  (callback: () => void): void;
  cancel: () => void;
}

/** Coalesces many stream callbacks into the latest callback in one frame. */
export function createRafBatcher(
  requestFrame: FrameCallback = (callback) => requestAnimationFrame(callback),
): RafBatcher {
  let frameId: number | null = null;
  let pending: (() => void) | null = null;

  const schedule = ((callback: () => void) => {
    pending = callback;
    if (frameId !== null) return;

    frameId = requestFrame(() => {
      frameId = null;
      const callbackToRun = pending;
      pending = null;
      callbackToRun?.();
    });
  }) as RafBatcher;

  schedule.cancel = () => {
    pending = null;
    frameId = null;
  };

  return schedule;
}
