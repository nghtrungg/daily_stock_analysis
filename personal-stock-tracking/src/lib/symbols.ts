const VIETNAM_SYMBOL = /^[A-Z0-9]{1,10}\.VN$/;

export function canonicaliseVietnamSymbol(value: string): string {
  return value.trim().toUpperCase();
}

export function isVietnamSymbol(value: string): boolean {
  return VIETNAM_SYMBOL.test(canonicaliseVietnamSymbol(value));
}

export function requireVietnamSymbol(value: string): string {
  const symbol = canonicaliseVietnamSymbol(value);

  if (!isVietnamSymbol(symbol)) {
    throw new Error('symbol must use the .VN suffix');
  }

  return symbol;
}
