const vndFormatter = new Intl.NumberFormat('vi-VN', {
  style: 'currency',
  currency: 'VND',
  maximumFractionDigits: 0
});

export function formatVnd(value: number): string {
  if (!Number.isFinite(value)) {
    return '—';
  }

  return vndFormatter.format(Math.round(value));
}
