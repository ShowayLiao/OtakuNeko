export function getTimelineSlotFromPointer(
  pointerOffset: number,
  slotHeight: number,
  totalSlots: number,
): number {
  if (!Number.isFinite(pointerOffset) || !Number.isFinite(slotHeight) || slotHeight <= 0 || totalSlots <= 0) {
    return 0;
  }

  const slot = Math.floor(Math.max(0, pointerOffset) / slotHeight);
  return Math.min(slot, Math.floor(totalSlots) - 1);
}

export function getTimelineSlotFromRect(
  pointerY: number,
  containerTop: number,
  slotHeight: number,
  totalSlots: number,
): number {
  if (!Number.isFinite(pointerY) || !Number.isFinite(containerTop)) return 0;
  return getTimelineSlotFromPointer(pointerY - containerTop, slotHeight, totalSlots);
}
