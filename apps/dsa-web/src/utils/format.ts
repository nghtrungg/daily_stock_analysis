export const formatDateTime = (value?: string | null, locale = 'en-US'): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

export const formatDate = (value?: string): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date);
};

export const toDateInputValue = (date: Date): string => {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/**
 * Returns the date N days ago as YYYY-MM-DD in Vietnam time.
 * Both ends of a date range use the same timezone as the local backend.
 */
export const getRecentStartDate = (days: number): string => {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(date);
};

/**
 * Returns today's date as YYYY-MM-DD in Vietnam time.
 * Use this instead of browser-local time to stay consistent with the backend.
 */
export const getTodayInVietnam = (): string =>
  new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date());

/** @deprecated Use getTodayInVietnam. Kept for source compatibility. */
export const getTodayInShanghai = getTodayInVietnam;

export const formatReportType = (value?: string): string => {
  if (!value) return '—';
  if (value === 'simple') return 'Standard';
  if (value === 'detailed') return 'Detailed';
  if (value === 'full') return 'Full';
  if (value === 'brief') return 'Brief';
  if (value === 'market_review') return 'Market review';
  return value;
};
