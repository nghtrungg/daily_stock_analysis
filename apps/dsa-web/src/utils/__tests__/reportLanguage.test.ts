import { describe, expect, it } from 'vitest';

import { getReportLocale, getReportText, normalizeReportLanguage } from '../reportLanguage';
import { getSentimentLabel } from '../../types/analysis';

describe('reportLanguage ko support', () => {
  it('normalizes ko and falls back to zh for unknown', () => {
    expect(normalizeReportLanguage('ko')).toBe('ko');
    expect(normalizeReportLanguage('en')).toBe('en');
    expect(normalizeReportLanguage('fr')).toBe('zh');
    expect(normalizeReportLanguage(undefined)).toBe('zh');
  });

  it('returns Korean report copy for ko', () => {
    const ko = getReportText('ko');
    expect(ko.keyInsights).toBe('핵심 인사이트');
    expect(ko.actionAdvice).toBe('대응 전략');
    expect(ko.fullReport).toBe('전체 분석 리포트');
  });

  it('keeps en report copy unchanged', () => {
    // expect(getReportText('zh').keyInsights).toBe('核心洞察');
    expect(getReportText('en').keyInsights).toBe('KEY INSIGHTS');
  });

  it('returns Korean sentiment labels by band', () => {
    expect(getSentimentLabel(90, 'ko')).toBe('매우 낙관');
    expect(getSentimentLabel(50, 'ko')).toBe('중립');
    expect(getSentimentLabel(10, 'ko')).toBe('매우 비관');
    expect(getSentimentLabel(90, 'en')).toBe('Very Bullish');
  });
});

describe('reportLanguage vi support', () => {
  it('normalizes Vietnamese and resolves its display locale', () => {
    expect(normalizeReportLanguage('vi')).toBe('vi');
    expect(getReportLocale('vi')).toBe('vi-VN');
  });

  it('returns Vietnamese report copy and sentiment labels', () => {
    const viText = getReportText('vi');

    expect(viText.keyInsights).toBe('NHẬN ĐỊNH CHÍNH');
    expect(viText.actionAdvice).toBe('Khuyến nghị hành động');
    expect(viText.fullReport).toBe('Báo cáo phân tích đầy đủ');
    expect(getSentimentLabel(90, 'vi')).toBe('Rất lạc quan');
    expect(getSentimentLabel(50, 'vi')).toBe('Trung lập');
    expect(getSentimentLabel(10, 'vi')).toBe('Rất bi quan');
  });
});
