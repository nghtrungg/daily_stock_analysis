const vietnamDateTimeFormatter = new Intl.DateTimeFormat('vi-VN', {
  timeZone: 'Asia/Ho_Chi_Minh',
  dateStyle: 'short',
  timeStyle: 'short'
});

const vietnamInputFormatter = new Intl.DateTimeFormat('sv-SE', {
  timeZone: 'Asia/Ho_Chi_Minh',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false
});

export function formatVietnamDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Không rõ thời điểm' : `${vietnamDateTimeFormatter.format(date)} ICT`;
}

export function toVietnamDateTimeInput(value: string | Date = new Date()): string {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return vietnamInputFormatter.format(date).replace(' ', 'T');
}

export function fromVietnamDateTimeInput(value: string): string {
  const date = new Date(`${value}:00+07:00`);
  if (Number.isNaN(date.getTime())) throw new Error('Thời điểm không hợp lệ.');
  return date.toISOString();
}
