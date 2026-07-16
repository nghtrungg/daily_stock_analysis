export type GithubDispatchConfig = {
  repository: string;
  workflowFile: string;
  workflowRef: string;
  token: string;
};

type Environment = Record<string, string | undefined>;

const repositoryPattern = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const workflowFilePattern = /^[A-Za-z0-9][A-Za-z0-9_.-]*\.ya?ml$/;
const workflowRefPattern = /^[A-Za-z0-9][A-Za-z0-9._/-]*$/;

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
