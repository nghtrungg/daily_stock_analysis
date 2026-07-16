export type GithubDispatchConfig = {
  repository: string;
  workflowFile: string;
  workflowRef: string;
  token: string;
};

export type GithubWorkflowDispatchResult = {
  externalRunId: string | null;
  externalRunUrl: string | null;
};

type Environment = Record<string, string | undefined>;

const repositoryPattern = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const workflowFilePattern = /^[A-Za-z0-9][A-Za-z0-9_.-]*\.ya?ml$/;
const workflowRefPattern = /^[A-Za-z0-9][A-Za-z0-9._/-]*$/;
const callbackTimeoutMilliseconds = 45 * 60 * 1_000;

function isSafeGithubRunUrl(value: unknown) {
  if (typeof value !== 'string' || value.length > 2_048) {
    return false;
  }

  try {
    const url = new URL(value);
    return url.protocol === 'https:'
      && (url.hostname === 'github.com' || url.hostname === 'api.github.com')
      && !url.username
      && !url.password;
  } catch {
    return false;
  }
}

export function readGithubDispatchConfig(environment: Environment): GithubDispatchConfig | null {
  const token = environment.GITHUB_ACTIONS_DISPATCH_TOKEN?.trim();
  const repository = environment.GITHUB_REPOSITORY?.trim();
  const workflowFile = environment.GITHUB_WORKFLOW_FILE?.trim();
  const workflowRef = environment.GITHUB_WORKFLOW_REF?.trim();

  if (!token || !repository || !workflowFile || !workflowRef) {
    return null;
  }

  if (!repositoryPattern.test(repository) || !workflowFilePattern.test(workflowFile) || !workflowRefPattern.test(workflowRef)) {
    return null;
  }

  return { repository, workflowFile, workflowRef, token };
}

export function createGithubWorkflowDispatch(config: GithubDispatchConfig, symbol: string, runId: string) {
  return {
    url: `https://api.github.com/repos/${config.repository}/actions/workflows/${encodeURIComponent(config.workflowFile)}/dispatches`,
    body: {
      ref: config.workflowRef,
      inputs: {
        stock_symbols: symbol,
        tracking_run_id: runId
      }
    }
  };
}

export function staleAnalysisRunCutoff(now: Date) {
  if (Number.isNaN(now.getTime())) throw new Error('Current time is invalid.');
  return new Date(now.getTime() - callbackTimeoutMilliseconds).toISOString();
}

export function parseGithubWorkflowDispatchResponse(status: number, body: string): GithubWorkflowDispatchResult {
  if (status < 200 || status >= 300) {
    throw new Error('GitHub Actions rejected the workflow dispatch.');
  }

  const trimmedBody = body.trim();
  if (!trimmedBody) {
    return { externalRunId: null, externalRunUrl: null };
  }

  let payload: unknown;
  try {
    payload = JSON.parse(trimmedBody);
  } catch {
    throw new Error('GitHub Actions returned an invalid workflow dispatch response.');
  }

  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('GitHub Actions returned an invalid workflow dispatch response.');
  }

  const response = payload as Record<string, unknown>;
  const workflowRunId = response.workflow_run_id;
  if (typeof workflowRunId !== 'number' || !Number.isSafeInteger(workflowRunId) || workflowRunId <= 0) {
    throw new Error('GitHub Actions returned an invalid workflow run identifier.');
  }

  const runUrl = isSafeGithubRunUrl(response.html_url)
    ? response.html_url
    : isSafeGithubRunUrl(response.run_url)
      ? response.run_url
      : null;

  if (!runUrl) {
    throw new Error('GitHub Actions returned an invalid workflow run URL.');
  }

  return { externalRunId: String(workflowRunId), externalRunUrl: runUrl as string };
}
