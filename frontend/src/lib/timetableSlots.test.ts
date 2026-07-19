import { describe, expect, it } from 'vitest';
import { getTimelineSlotFromPointer, getTimelineSlotFromRect } from './timetableSlots';

describe('getTimelineSlotFromPointer', () => {
  it('maps a pointer position to the bounded 20-minute slot', () => {
    expect(getTimelineSlotFromPointer(0, 40, 24)).toBe(0);
    expect(getTimelineSlotFromPointer(39.9, 40, 24)).toBe(0);
    expect(getTimelineSlotFromPointer(40, 40, 24)).toBe(1);
    expect(getTimelineSlotFromPointer(999, 40, 24)).toBe(23);
  });

  it('handles invalid geometry without returning an invalid slot', () => {
    expect(getTimelineSlotFromPointer(100, 0, 24)).toBe(0);
    expect(getTimelineSlotFromPointer(-10, 40, 24)).toBe(0);
  });

  it('maps a dragged rectangle center relative to a day column', () => {
    expect(getTimelineSlotFromRect(240, 80, 40, 24)).toBe(4);
    expect(getTimelineSlotFromRect(80, 80, 40, 24)).toBe(0);
  });
});
