export class TextRevealBuffer {
  private pending = '';

  append(text: string) {
    this.pending += text;
  }

  take(maxCharacters: number) {
    if (maxCharacters <= 0 || this.pending.length === 0) return '';
    let endIndex = 0;
    let characterCount = 0;
    for (const character of this.pending) {
      if (characterCount >= maxCharacters) break;
      endIndex += character.length;
      characterCount += 1;
    }
    const revealed = this.pending.slice(0, endIndex);
    this.pending = this.pending.slice(endIndex);
    return revealed;
  }

  get length() {
    return this.pending.length;
  }

  hasPending() {
    return this.pending.length > 0;
  }

  clear() {
    this.pending = '';
  }
}

export type RevealField = 'details' | 'output';

export interface TextRevealUpdate {
  nodeId: string;
  field: RevealField;
  text: string;
}

export function revealCharactersPerFrame(backlog: number) {
  if (backlog > 800) return 16;
  if (backlog > 320) return 10;
  if (backlog > 120) return 6;
  if (backlog > 40) return 3;
  return 1;
}

export class KeyedTextRevealQueue {
  private buffers = new Map<string, {
    nodeId: string;
    field: RevealField;
    buffer: TextRevealBuffer;
  }>();

  append(nodeId: string, field: RevealField, text: string) {
    if (!text) return;
    const key = `${nodeId}:${field}`;
    const entry = this.buffers.get(key) ?? {
      nodeId,
      field,
      buffer: new TextRevealBuffer(),
    };
    entry.buffer.append(text);
    this.buffers.set(key, entry);
  }

  takeFrame(
    frameSize: (backlog: number) => number = revealCharactersPerFrame,
  ): TextRevealUpdate[] {
    const updates: TextRevealUpdate[] = [];
    for (const [key, entry] of this.buffers) {
      const text = entry.buffer.take(frameSize(entry.buffer.length));
      if (text) updates.push({ nodeId: entry.nodeId, field: entry.field, text });
      if (!entry.buffer.hasPending()) this.buffers.delete(key);
    }
    return updates;
  }

  hasPending(nodeId?: string) {
    if (!nodeId) return this.buffers.size > 0;
    for (const entry of this.buffers.values()) {
      if (entry.nodeId === nodeId) return true;
    }
    return false;
  }

  clear() {
    this.buffers.clear();
  }
}
