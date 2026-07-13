import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { historyApi } from '../../../api/history';
import { ReportMarkdown } from '../ReportMarkdown';

vi.mock('../../../api/history', () => ({
  historyApi: {
    getMarkdown: vi.fn(),
  },
}));

describe('ReportMarkdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('uses localized copy labels for English reports', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Full report');

    render(
      <ReportMarkdown
        recordId={1}
        stockName="Apple"
        stockCode="AAPL"
        reportLanguage="en"
        onClose={() => {}}
      />
    );

    expect(await screen.findByRole('button', { name: 'Copy Markdown Source' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Copy Plain Text' })).toBeInTheDocument();
  });

  it('uses localized copy labels for Vietnamese reports', async () => {
    vi.mocked(historyApi.getMarkdown).mockResolvedValue('# Báo cáo đầy đủ');

    render(
      <ReportMarkdown
        recordId={2}
        stockName="FPT"
        stockCode="FPT"
        reportLanguage="vi"
        onClose={() => {}}
      />
    );

    expect(await screen.findByRole('button', { name: 'Sao chép nguồn Markdown' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sao chép văn bản thuần' })).toBeInTheDocument();
  });
});
