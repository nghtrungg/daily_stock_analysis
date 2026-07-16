import { describe, expect, it } from '@jest/globals';
import {
  createGithubWorkflowDispatch,
  parseGithubWorkflowDispatchResponse,
  readGithubDispatchConfig,
  staleAnalysisRunCutoff
} from './github-dispatch';

describe('GitHub Actions dispatch contract', () => {
  it('creates a repository-scoped workflow dispatch for the selected Vietnam symbol', () => {
    const config = readGithubDispatchConfig({
      GITHUB_ACTIONS_DISPATCH_TOKEN: 'token',
      GITHUB_REPOSITORY: 'nghtrungg/daily_stock_analysis',
      GITHUB_WORKFLOW_FILE: '00-daily-analysis.yml',
      GITHUB_WORKFLOW_REF: 'remote_user'
    });

    expect(config).not.toBeNull();
    expect(createGithubWorkflowDispatch(config!, 'VNM.VN', 'a59a1476-2ea4-4c86-9a3c-d0df438e8102')).toEqual({
      url: 'https://api.github.com/repos/nghtrungg/daily_stock_analysis/actions/workflows/00-daily-analysis.yml/dispatches',
      body: {
        ref: 'remote_user',
        inputs: {
          stock_symbols: 'VNM.VN',
          tracking_run_id: 'a59a1476-2ea4-4c86-9a3c-d0df438e8102'
        }
      }
    });
  });

  it('rejects malformed repository and workflow configuration', () => {
    expect(readGithubDispatchConfig({
      GITHUB_ACTIONS_DISPATCH_TOKEN: 'token',
      GITHUB_REPOSITORY: 'https://github.com/nghtrungg/daily_stock_analysis',
      GITHUB_WORKFLOW_FILE: '../workflow.yml',
      GITHUB_WORKFLOW_REF: 'main'
    })).toBeNull();
  });

  it('records the workflow run metadata returned by the current GitHub API', () => {
    expect(parseGithubWorkflowDispatchResponse(200, JSON.stringify({
      workflow_run_id: 987654321,
      run_url: 'https://api.github.com/repos/nghtrungg/daily_stock_analysis/actions/runs/987654321',
      html_url: 'https://github.com/nghtrungg/daily_stock_analysis/actions/runs/987654321'
    }))).toEqual({
      externalRunId: '987654321',
      externalRunUrl: 'https://github.com/nghtrungg/daily_stock_analysis/actions/runs/987654321'
    });
  });

  it('keeps legacy empty successful dispatch responses compatible', () => {
    expect(parseGithubWorkflowDispatchResponse(204, '')).toEqual({
      externalRunId: null,
      externalRunUrl: null
    });
  });

  it('rejects malformed or unsafe dispatch metadata', () => {
    expect(() => parseGithubWorkflowDispatchResponse(200, '{')).toThrow('invalid workflow dispatch response');
    expect(() => parseGithubWorkflowDispatchResponse(200, JSON.stringify({
      workflow_run_id: 12,
      html_url: 'https://attacker.example/actions/runs/12'
    }))).toThrow('invalid workflow run URL');
    expect(() => parseGithubWorkflowDispatchResponse(500, '')).toThrow('rejected');
  });

  it('uses the exact 45-minute stale callback boundary', () => {
    expect(staleAnalysisRunCutoff(new Date('2026-07-16T08:45:00.000Z'))).toBe('2026-07-16T08:00:00.000Z');
  });
});
