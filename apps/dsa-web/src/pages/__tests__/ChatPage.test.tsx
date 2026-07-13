import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { createParsedApiError } from '../../api/error';
import { UiLanguageProvider } from '../../contexts/UiLanguageContext';
import type { Message, ProgressStep } from '../../stores/agentChatStore';
import { extractStockCodeFromMessage, extractStockCodesFromMessage } from '../../utils/chatStockCode';
import ChatPage from '../ChatPage';

const {
  mockGetSkills,
  mockDeleteChatSession,
  mockSendChat,
  mockGetSystemConfig,
  mockUpdateSystemConfig,
  mockGetWatchlist,
  mockAddToWatchlist,
  mockRemoveFromWatchlist,
  mockDownloadSession,
  mockFormatSessionAsMarkdown,
  mockGetHistoryDetail,
} = vi.hoisted(() => ({
  mockGetSkills: vi.fn(),
  mockDeleteChatSession: vi.fn(),
  mockSendChat: vi.fn(),
  mockGetSystemConfig: vi.fn(),
  mockUpdateSystemConfig: vi.fn(),
  mockGetWatchlist: vi.fn(),
  mockAddToWatchlist: vi.fn(),
  mockRemoveFromWatchlist: vi.fn(),
  mockDownloadSession: vi.fn(),
  mockFormatSessionAsMarkdown: vi.fn(),
  mockGetHistoryDetail: vi.fn(),
}));

const mockLoadSessions = vi.fn();
const mockLoadInitialSession = vi.fn();
const mockSwitchSession = vi.fn();
const mockStartStream = vi.fn();
const mockClearCompletionBadge = vi.fn();
const mockStartNewChat = vi.fn();

const mockStoreState = {
  messages: [] as Message[],
  loading: false,
  progressSteps: [] as ProgressStep[],
  sessionId: 'session-1',
  sessions: [
    {
      session_id: 'session-1',
      title: 'Analyze VNM.VN',
      message_count: 2,
      created_at: '2026-07-13T02:00:00Z',
      last_active: '2026-07-13T02:05:00Z',
    },
  ],
  sessionsLoading: false,
  chatError: null,
  loadSessions: mockLoadSessions,
  loadInitialSession: mockLoadInitialSession,
  switchSession: mockSwitchSession,
  startStream: mockStartStream,
  clearCompletionBadge: mockClearCompletionBadge,
};

vi.mock('../../api/agent', () => ({
  agentApi: {
    getSkills: mockGetSkills,
    deleteChatSession: mockDeleteChatSession,
    sendChat: mockSendChat,
  },
}));

vi.mock('../../api/systemConfig', () => ({
  systemConfigApi: {
    getConfig: mockGetSystemConfig,
    update: mockUpdateSystemConfig,
    getWatchlist: mockGetWatchlist,
    addToWatchlist: mockAddToWatchlist,
    removeFromWatchlist: mockRemoveFromWatchlist,
  },
}));

vi.mock('../../utils/chatExport', () => ({
  downloadSession: mockDownloadSession,
  formatSessionAsMarkdown: mockFormatSessionAsMarkdown,
}));

vi.mock('../../api/history', () => ({
  historyApi: {
    getDetail: mockGetHistoryDetail,
  },
}));

vi.mock('../../stores/agentChatStore', () => {
  const useAgentChatStore = (
    selector?: (state: typeof mockStoreState) => unknown,
  ) => (typeof selector === 'function' ? selector(mockStoreState) : mockStoreState);

  useAgentChatStore.getState = () => ({
    startNewChat: mockStartNewChat,
  });

  return { useAgentChatStore };
});

function renderChat(initialEntry = '/chat') {
  return render(
    <UiLanguageProvider lockedLanguage="en">
      <MemoryRouter initialEntries={[initialEntry]}>
        <ChatPage />
      </MemoryRouter>
    </UiLanguageProvider>,
  );
}

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-color-scheme: dark)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });

  Object.defineProperty(window, 'requestAnimationFrame', {
    writable: true,
    value: (callback: FrameRequestCallback) => window.setTimeout(() => callback(0), 0),
  });

  Object.defineProperty(window, 'cancelAnimationFrame', {
    writable: true,
    value: (handle: number) => window.clearTimeout(handle),
  });

  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    writable: true,
    value: vi.fn(),
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  mockStoreState.messages = [];
  mockStoreState.loading = false;
  mockStoreState.progressSteps = [];
  mockStoreState.chatError = null;
  mockStoreState.sessionsLoading = false;
  mockStoreState.sessionId = 'session-1';
  mockStoreState.sessions = [
    {
      session_id: 'session-1',
      title: 'Analyze VNM.VN',
      message_count: 2,
      created_at: '2026-07-13T02:00:00Z',
      last_active: '2026-07-13T02:05:00Z',
    },
  ];
  mockGetSkills.mockResolvedValue({
    skills: [
      { id: 'bull_trend', name: 'Trend analysis', description: 'Trend-focused analysis' },
    ],
    default_skill_id: 'bull_trend',
  });
  mockDeleteChatSession.mockResolvedValue(undefined);
  mockSendChat.mockResolvedValue({ success: true });
  mockGetWatchlist.mockResolvedValue([]);
  mockAddToWatchlist.mockResolvedValue([]);
  mockRemoveFromWatchlist.mockResolvedValue([]);
  mockGetHistoryDetail.mockResolvedValue({});
  mockGetSystemConfig.mockResolvedValue({
    configVersion: 'cfg-v1',
    maskToken: 'mask-token',
    items: [
      {
        key: 'AGENT_CONTEXT_COMPRESSION_ENABLED',
        value: 'false',
        rawValueExists: true,
        isMasked: false,
      },
    ],
  });
  mockUpdateSystemConfig.mockResolvedValue({
    success: true,
    configVersion: 'cfg-v2',
    appliedCount: 1,
    skippedMaskedCount: 0,
    reloadTriggered: true,
    updatedKeys: ['AGENT_CONTEXT_COMPRESSION_ENABLED'],
    warnings: [],
  });
  mockDownloadSession.mockImplementation(() => undefined);
  mockFormatSessionAsMarkdown.mockReturnValue('# Exported Vietnam stock conversation');
});

describe('ChatPage English Vietnam contract', () => {
  it('renders the English workspace shell and Vietnam-specific empty state', async () => {
    renderChat();

    expect(await screen.findByTestId('chat-workspace')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Stock Assistant' })).toBeInTheDocument();
    expect(screen.getByText('Ask AI about Vietnamese stocks for skill-driven analysis, trading guidance, and real-time decision reports.')).toBeInTheDocument();
    expect(screen.getByText('Start a stock analysis')).toBeInTheDocument();
    expect(screen.getByText('Enter “Analyze VNM.VN” or “Is FPT.VN a buy now?” and the AI will use real-time data tools to create a decision report.')).toBeInTheDocument();
    expect(screen.getByText(/Jul/)).toBeInTheDocument();
    expect(screen.queryByText(/[一-龥]/)).not.toBeInTheDocument();
    expect(screen.queryByText('问股')).not.toBeInTheDocument();
    expect(mockLoadInitialSession).toHaveBeenCalled();
    expect(mockClearCompletionBadge).toHaveBeenCalled();
  });

  it('loads and saves the global context-compression setting', async () => {
    renderChat();

    const compressionToggle = await screen.findByRole('checkbox', { name: /Context compression/ });
    await waitFor(() => expect(compressionToggle).not.toBeDisabled());
    expect(compressionToggle).not.toBeChecked();

    fireEvent.click(compressionToggle);

    await waitFor(() => {
      expect(mockUpdateSystemConfig).toHaveBeenCalledWith({
        configVersion: 'cfg-v1',
        maskToken: 'mask-token',
        reloadNow: true,
        items: [
          {
            key: 'AGENT_CONTEXT_COMPRESSION_ENABLED',
            value: 'true',
          },
        ],
      });
    });
    expect(compressionToggle).toBeChecked();
    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });

  it('rolls back context compression when saving fails', async () => {
    mockGetSystemConfig.mockResolvedValue({
      configVersion: 'cfg-v1',
      maskToken: 'mask-token',
      items: [
        {
          key: 'AGENT_CONTEXT_COMPRESSION_ENABLED',
          value: 'true',
          rawValueExists: true,
          isMasked: false,
        },
      ],
    });
    mockUpdateSystemConfig.mockRejectedValue(
      createParsedApiError({
        title: 'Save failed',
        message: 'Configuration service unavailable',
        category: 'unknown',
      }),
    );
    renderChat();

    const compressionToggle = await screen.findByRole('checkbox', { name: /Context compression/ });
    await waitFor(() => expect(compressionToggle).toBeChecked());
    fireEvent.click(compressionToggle);

    await waitFor(() => expect(compressionToggle).toBeChecked());
    expect(screen.getByText('Configuration service unavailable')).toBeInTheDocument();
  });

  it('does not switch the current session and opens an English deletion confirmation', async () => {
    renderChat();

    const sessionCard = await screen.findByRole('button', {
      name: 'Switch to conversation Analyze VNM.VN',
    });
    fireEvent.click(sessionCard);
    expect(mockSwitchSession).not.toHaveBeenCalled();
    expect(sessionCard).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: 'Delete conversation Analyze VNM.VN' }));
    expect(await screen.findByText('This conversation cannot be recovered after deletion. Continue?')).toBeInTheDocument();
  });

  it('hides message actions when there are no messages', async () => {
    renderChat();

    expect(await screen.findByRole('heading', { name: 'Stock Assistant' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Export the conversation as a Markdown file' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send to the configured notification bot or email' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Conversation history' })).toBeInTheDocument();
  });

  it('exports and sends the current session through English header actions', async () => {
    mockStoreState.messages = [
      { id: 'user-1', role: 'user', content: 'Analyze VNM.VN' },
      { id: 'assistant-1', role: 'assistant', content: 'The trend is constructive.', skillName: 'Trend analysis' },
    ];
    renderChat();

    fireEvent.click(await screen.findByRole('button', { name: 'Export the conversation as a Markdown file' }));
    expect(mockDownloadSession).toHaveBeenCalledWith(mockStoreState.messages);

    fireEvent.click(screen.getByRole('button', { name: 'Send to the configured notification bot or email' }));
    await waitFor(() => expect(mockSendChat).toHaveBeenCalledWith('# Exported Vietnam stock conversation'));
    expect(await screen.findByText('Sent to the notification channel')).toBeInTheDocument();
  });

  it('selects English skills and sends a Vietnam ticker in order', async () => {
    mockGetSkills.mockResolvedValue({
      skills: [
        { id: 'bull_trend', name: 'Trend analysis', description: 'Trend-focused analysis' },
        { id: 'ma_golden_cross', name: 'Moving-average golden cross', description: 'Moving-average analysis' },
      ],
      default_skill_id: 'bull_trend',
    });
    renderChat();

    expect(await screen.findByRole('checkbox', { name: 'Trend analysis' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'General analysis' })).not.toBeChecked();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Moving-average golden cross' }));
    fireEvent.change(screen.getByPlaceholderText(/Example: Analyze VNM\.VN/), {
      target: { value: 'Analyze FPT.VN' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(mockStartStream).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Analyze FPT.VN',
          skills: ['bull_trend', 'ma_golden_cross'],
          context: expect.objectContaining({ stock_code: 'FPT.VN' }),
        }),
        {
          skillNames: ['Trend analysis', 'Moving-average golden cross'],
          skillName: 'Trend analysis, Moving-average golden cross',
        },
      );
    });
  });

  it('renders failure and budget-skip progress as non-success states', async () => {
    mockStoreState.loading = true;
    mockStoreState.progressSteps = [
      { type: 'stage_done', stage: 'risk', status: 'failed' },
      { type: 'pipeline_budget_skipped', stage: 'decision' },
    ];
    mockStoreState.messages = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Partial answer',
        thinkingSteps: [
          { type: 'stage_done', stage: 'risk', status: 'failed' },
          { type: 'pipeline_budget_skipped', stage: 'decision' },
        ],
      },
    ];
    const { container } = renderChat();

    expect(await screen.findAllByText('decision skipped: insufficient budget')).toHaveLength(1);
    const thinkingToggle = container.querySelector('button[class*="mb-2"][class*="w-full"]') as HTMLButtonElement;
    fireEvent.click(thinkingToggle);

    const failedStage = screen.getAllByText('risk failed').find((node) => node.closest('.chat-progress-item'));
    const budgetSkipped = screen.getAllByText('decision skipped: insufficient budget').find((node) => node.closest('.chat-progress-item'));
    expect(failedStage?.closest('.chat-progress-item')).toHaveClass('chat-progress-item-danger');
    expect(budgetSkipped?.closest('.chat-progress-item')).toHaveClass('chat-progress-item-muted');
  });

  it('hydrates a Vietnam report follow-up with actual-VND context', async () => {
    mockGetHistoryDetail.mockResolvedValue({
      meta: {
        id: 7,
        queryId: 'q-7',
        stockCode: 'VNM.VN',
        stockName: 'Vinamilk',
        reportType: 'detailed',
        reportLanguage: 'vi',
        createdAt: '2026-07-13T07:00:00+07:00',
        currentPrice: 56600,
        changePct: 1.2,
      },
      summary: {
        analysisSummary: 'Xu hướng tăng thận trọng',
        operationAdvice: 'Theo dõi',
        trendPrediction: 'Tích lũy',
        sentimentScore: 68,
      },
      strategy: { stopLoss: '53,000 VND' },
    });
    renderChat('/chat?stock=VNM.VN&name=Vinamilk&recordId=7');

    expect(await screen.findByDisplayValue('Provide a deeper analysis of Vinamilk(VNM.VN)')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText('Historical analysis context is loading; you can send the follow-up now.')).not.toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(mockStartStream).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Provide a deeper analysis of Vinamilk(VNM.VN)',
          context: expect.objectContaining({
            stock_code: 'VNM.VN',
            stock_name: 'Vinamilk',
            previous_price: 56600,
            previous_change_pct: 1.2,
            previous_strategy: { stopLoss: '53,000 VND' },
          }),
        }),
        expect.objectContaining({ skillName: 'Trend analysis' }),
      );
    });
  });

  it('switches active context only to another Vietnam ticker', async () => {
    renderChat('/chat?stock=VNM.VN&name=Vinamilk');
    const textarea = await screen.findByDisplayValue('Provide a deeper analysis of Vinamilk(VNM.VN)');

    fireEvent.change(textarea, { target: { value: 'Switch to FPT.VN' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(mockStartStream).toHaveBeenLastCalledWith(
        expect.objectContaining({
          message: 'Switch to FPT.VN',
          context: { stock_code: 'FPT.VN', stock_name: null },
        }),
        expect.any(Object),
      );
    });
  });

  it('rejects malformed or foreign follow-up query parameters', async () => {
    renderChat('/chat?stock=AAPL.US&name=Bad%0AName&recordId=abc');

    expect(await screen.findByRole('heading', { name: 'Stock Assistant' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Example: Analyze VNM\.VN/)).toHaveValue('');
    expect(mockGetHistoryDetail).not.toHaveBeenCalled();
  });

  it('shows a jump-to-latest action when content arrives away from the bottom', async () => {
    mockStoreState.messages = [
      { id: 'user-1', role: 'user', content: 'Analyze VNM.VN' },
      { id: 'assistant-1', role: 'assistant', content: 'Initial result', skillName: 'Trend analysis' },
    ];
    const { rerender } = renderChat();

    const viewport = await screen.findByTestId('chat-message-scroll');
    Object.defineProperty(viewport, 'scrollTop', { configurable: true, value: 0 });
    Object.defineProperty(viewport, 'clientHeight', { configurable: true, value: 400 });
    Object.defineProperty(viewport, 'scrollHeight', { configurable: true, value: 1200 });
    fireEvent.scroll(viewport);

    mockStoreState.messages = [
      ...mockStoreState.messages,
      { id: 'assistant-2', role: 'assistant', content: 'Additional result', skillName: 'Trend analysis' },
    ];
    rerender(
      <UiLanguageProvider lockedLanguage="en">
        <MemoryRouter initialEntries={['/chat']}>
          <ChatPage />
        </MemoryRouter>
      </UiLanguageProvider>,
    );

    const jumpButton = await screen.findByRole('button', { name: 'View the latest message' });
    fireEvent.click(jumpButton);
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
  });
});

describe('Vietnam-only chat ticker extraction', () => {
  it('normalizes bare and explicit Vietnam tickers', () => {
    expect(extractStockCodeFromMessage('Analyze VNM')).toBe('VNM.VN');
    expect(extractStockCodeFromMessage('Analyze FPT.VN')).toBe('FPT.VN');
    expect(extractStockCodesFromMessage('Compare VNM.VN and HPG.VN')).toEqual(['VNM.VN', 'HPG.VN']);
  });

  it('rejects US, Chinese, and Hong Kong codes', () => {
    expect(extractStockCodeFromMessage('Analyze AAPL.US')).toBeNull();
    expect(extractStockCodeFromMessage('Analyze 600519.SH')).toBeNull();
    expect(extractStockCodeFromMessage('Analyze 00700.HK')).toBeNull();
    expect(extractStockCodesFromMessage('Compare AAPL.US and 600519.SH')).toEqual([]);
  });

  it('does not treat currencies or indicator abbreviations as Vietnam tickers', () => {
    expect(extractStockCodeFromMessage('Price in VND')).toBeNull();
    expect(extractStockCodeFromMessage('How is RSI?')).toBeNull();
    expect(extractStockCodesFromMessage('Compare the MA moving average with MACD')).toEqual([]);
  });
});

describe('Vietnam watchlist action', () => {
  it('recognizes a bare Vietnam ticker as an existing .VN watchlist item', async () => {
    mockGetWatchlist.mockResolvedValue(['VNM.VN']);
    renderChat();

    const textarea = await screen.findByPlaceholderText(/Example: Analyze VNM\.VN/);
    fireEvent.change(textarea, { target: { value: 'Analyze VNM' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(await screen.findByText('Remove from watchlist')).toBeInTheDocument();
  });
});
