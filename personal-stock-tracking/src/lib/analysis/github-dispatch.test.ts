import { describe, expect, it } from '@jest/globals';
import { createGithubWorkflowDispatch, readGithubDispatchConfig } from './github-dispatch';

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
});
