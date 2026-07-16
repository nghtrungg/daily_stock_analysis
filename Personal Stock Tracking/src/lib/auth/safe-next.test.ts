import { describe, expect, it } from '@jest/globals';
import { safeNextPath } from './safe-next';

describe('safeNextPath', () => {
  it('keeps an internal destination after magic-link confirmation', () => {
    expect(safeNextPath('/watchlist')).toBe('/watchlist');
  });

  it('rejects an external or protocol-relative destination', () => {
    expect(safeNextPath('https://attacker.example')).toBe('/');
    expect(safeNextPath('//attacker.example')).toBe('/');
  });
});
