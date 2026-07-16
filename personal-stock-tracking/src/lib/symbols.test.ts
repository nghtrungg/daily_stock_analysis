import { describe, expect, it } from '@jest/globals';
import { canonicaliseVietnamSymbol, isVietnamSymbol } from './symbols';

describe('Vietnam stock symbols', () => {
  it('canonicalises a lower-case, padded symbol to the required .VN form', () => {
    expect(canonicaliseVietnamSymbol('  vnm.vn ')).toBe('VNM.VN');
  });

  it('rejects a symbol without the Vietnam market suffix', () => {
    expect(isVietnamSymbol('VNM')).toBe(false);
  });

  it('rejects a symbol with unsupported punctuation', () => {
    expect(isVietnamSymbol('VNM-VN')).toBe(false);
  });
});
