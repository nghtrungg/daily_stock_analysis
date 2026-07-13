interface ValidationResult {
  valid: boolean;
  message?: string;
  normalized: string;
}

const SUPPORTED_QUERY_CHARACTERS = /^[\p{L}0-9.&,'()\-\s]+$/u;

const STOCK_CODE_PATTERNS = [
  /^[A-Z0-9]{2,10}\.VN$/,
  /^[A-Z]{2,5}$/, // Convenience input; normalized to the explicit .VN form.
];

/**
 * Check whether the input looks like a stock code.
 */
export const looksLikeStockCode = (value: string): boolean => {
  const normalized = value.trim().toUpperCase();
  return STOCK_CODE_PATTERNS.some((regex) => regex.test(normalized));
};

/**
 * Validate Vietnam stock codes and normalize bare tickers to the .VN form.
 */
export const validateStockCode = (value: string): ValidationResult => {
  let normalized = value.trim().toUpperCase();

  if (!normalized) {
    return { valid: false, message: 'Enter a Vietnam stock code', normalized };
  }

  const valid = looksLikeStockCode(normalized);
  if (valid && /^[A-Z]{2,5}$/.test(normalized)) {
    normalized = `${normalized}.VN`;
  }

  return {
    valid,
    message: valid ? undefined : 'Use a Vietnam ticker such as VNM.VN',
    normalized,
  };
};

/**
 * Reject obviously invalid free-text queries before they reach the backend.
 */
export const isObviouslyInvalidStockQuery = (value: string): boolean => {
  const normalized = value.trim().toUpperCase();

  if (!normalized || looksLikeStockCode(normalized)) {
    return false;
  }

  if (!SUPPORTED_QUERY_CHARACTERS.test(normalized)) {
    return true;
  }

  const hasLetters = /[A-Z]/.test(normalized);
  const hasDigits = /\d/.test(normalized);

  return hasLetters && hasDigits;
};
