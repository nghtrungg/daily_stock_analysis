import { describe, expect, test } from 'vitest';
import {
  isObviouslyInvalidStockQuery,
  looksLikeStockCode,
  validateStockCode,
} from '../validation';

describe('stock code validation', () => {
  test.each([
    ['VNM.VN', 'VNM.VN'],
    ['mbb.vn', 'MBB.VN'],
    ['FPT', 'FPT.VN'],
  ])('accepts Vietnam stock code %s', (input, normalized) => {
    expect(looksLikeStockCode(input)).toBe(true);
    expect(validateStockCode(input)).toEqual({
      valid: true,
      normalized,
    });
    expect(isObviouslyInvalidStockQuery(input)).toBe(false);
  });

  test.each(['AAPL.US', '600519', '00700.HK', '005930.KS'])(
    'rejects foreign-market stock code %s',
    (input) => {
      const result = validateStockCode(input);
      expect(result.valid).toBe(false);
    }
  );

  test('allows Vietnamese company names with diacritics as free text', () => {
    expect(isObviouslyInvalidStockQuery('Công ty Cổ phần Sữa Việt Nam')).toBe(false);
  });
});
