import type { AnalysisRun } from './portfolio-store';

const statusLabels = {
  queued: 'Đang chờ',
  dispatched: 'Đã gửi',
  running: 'Đang phân tích',
  succeeded: 'Hoàn tất',
  failed: 'Thất bại'
} as const;

export function analysisStatusLabel(run?: AnalysisRun): string {
  return run ? statusLabels[run.status] : 'Chưa từng phân tích';
}

export function analysisActionLabel(state: 'ready' | 'requesting' | 'in-progress' | 'cooldown'): string {
  if (state === 'requesting') return 'Đang gửi yêu cầu…';
  if (state === 'in-progress') return 'Đang phân tích';
  if (state === 'cooldown') return 'Sắp có thể yêu cầu lại';
  return 'Phân tích';
}

export function analysisNote(run?: AnalysisRun): string {
  if (run?.summary) return run.summary;
  if (run?.status === 'failed') return 'Không thể hoàn tất lần phân tích gần nhất. Bạn có thể thử lại sau một phút.';
  if (run) return 'Phân tích đang được xử lý qua dịch vụ bảo mật.';
  return 'Yêu cầu một bản phân tích mới qua dịch vụ bảo mật.';
}
