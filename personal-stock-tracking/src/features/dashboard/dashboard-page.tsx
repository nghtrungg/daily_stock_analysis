'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import {
  BarChart3,
  Eye,
  Plus,
  WalletCards
} from 'lucide-react';
import { AppShell } from '../../components/app-shell';
import { formatVnd } from '../../lib/money';
import { analysisActionLabel, analysisNote, analysisStatusLabel } from '../portfolio/analysis-messages';
import { usePortfolio } from '../portfolio/portfolio-provider';

type TransactionFields = {
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
};

function StateChip({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'quiet' }) {
  return <span className={`state-chip state-chip--${tone}`}>{children}</span>;
}

export function DashboardPage() {
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const { addBuyTransaction, analysisRequestStateFor, errorMessage, isLoading, isMutating, latestAnalysisFor, positions, requestAnalysis, totalCostVnd } = usePortfolio();
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset
  } = useForm<TransactionFields>({
    defaultValues: { symbol: '', quantity: undefined, unitPriceVnd: undefined, feeVnd: 0 }
  });

  function closeForm() {
    setIsFormOpen(false);
    setFormError(null);
  }

  async function saveTransaction(fields: TransactionFields) {
    try {
      await addBuyTransaction(fields);
      closeForm();
      reset();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Không thể lưu giao dịch.');
    }
  }

  async function analyzeSymbol(symbol: string) {
    try {
      await requestAnalysis(symbol);
    } catch {
      // The shared provider renders a user-safe error below the holdings list.
    }
  }

  return (
    <AppShell
      activePath="/"
      action={(
        <button className="button button--primary" disabled={isMutating} type="button" onClick={() => setIsFormOpen(true)}>
          <Plus aria-hidden="true" size={17} strokeWidth={2.2} />
          <span>Ghi giao dịch</span>
        </button>
      )}
    >

      <section className="portfolio-lead" aria-labelledby="dashboard-title">
        <div>
          <p className="utility-label">Danh mục cá nhân · VND</p>
          <h1 id="dashboard-title">Tổng quan danh mục</h1>
        </div>
        <p className="lead-copy">Ghi sổ giao dịch trước. Trang này tính giá vốn từ giao dịch của bạn và luôn nêu rõ khi chưa có dữ liệu thị trường.</p>
      </section>

      <section className="summary-grid" aria-label="Tóm tắt danh mục">
        <article className="summary-card summary-card--emphasis">
          <span>Tổng giá vốn</span>
          <strong>{formatVnd(totalCostVnd)}</strong>
          <small>Từ các giao dịch mua đã ghi</small>
        </article>
        <article className="summary-card">
          <span>Giá trị thị trường</span>
          <strong>—</strong>
          <small>Chưa có giá gần nhất</small>
        </article>
        <article className="summary-card">
          <span>Lãi/lỗ chưa thực hiện</span>
          <strong>—</strong>
          <small>Cần giá gần nhất</small>
        </article>
      </section>

      <section className="workbench" aria-labelledby="holdings-title">
        <div className="section-heading">
          <div>
            <p className="utility-label">Vị thế hiện tại</p>
            <h2 id="holdings-title">Khoản nắm giữ</h2>
          </div>
          <span className="local-indicator">{isLoading ? 'Đang đồng bộ' : 'Đã đồng bộ an toàn'}</span>
        </div>

        {isLoading ? (
          <div className="loading-frame" role="status" aria-label="Đang tải danh mục">
            <div className="loading-frame__heading">
              <span className="skeleton skeleton--mark" aria-hidden="true" />
              <div>
                <span className="skeleton skeleton--title" aria-hidden="true" />
                <span className="skeleton skeleton--copy" aria-hidden="true" />
              </div>
            </div>
            <span className="skeleton skeleton--panel" aria-hidden="true" />
            <span className="visually-hidden">Đang tải danh mục của bạn.</span>
          </div>
        ) : positions.length === 0 ? (
          <section className="empty-frame" aria-label="Danh mục trống">
            <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={28} strokeWidth={1.5} /></div>
            <div className="empty-frame__copy">
              <h3>Chưa có khoản nắm giữ</h3>
              <p>Giao dịch mua đầu tiên sẽ tạo một khoản nắm giữ và tính giá vốn bình quân gia quyền.</p>
            </div>
            <div className="state-list" aria-label="Trạng thái dữ liệu">
              <StateChip><Eye aria-hidden="true" size={14} />Giá: Chưa có</StateChip>
              <StateChip tone="quiet"><BarChart3 aria-hidden="true" size={14} />Phân tích: Chưa từng phân tích</StateChip>
            </div>
            <button className="button button--secondary" disabled={isMutating} type="button" onClick={() => setIsFormOpen(true)}>
              Ghi giao dịch
            </button>
          </section>
        ) : (
          <div className="holding-list" aria-label="Các khoản nắm giữ">
            {positions.map((position) => {
              const run = latestAnalysisFor(position.symbol);
              const requestState = analysisRequestStateFor(position.symbol);
              const note = analysisNote(run);

              return (
              <article className="holding-frame" key={position.symbol}>
                <div className="holding-frame__identity">
                  <span className="ticker-mark" aria-hidden="true">VN</span>
                  <div>
                    <h3>{position.symbol}</h3>
                    <p>Nắm giữ · {position.quantity} cổ phiếu</p>
                  </div>
                </div>
                <dl className="holding-frame__metrics">
                  <div><dt>Giá vốn bình quân</dt><dd>{formatVnd(position.averageCostVnd)}</dd></div>
                  <div><dt>Giá trị thị trường</dt><dd>—</dd></div>
                </dl>
                <div className="holding-frame__states">
                  <StateChip><Eye aria-hidden="true" size={14} />Giá: Chưa có</StateChip>
                  <StateChip tone="quiet"><BarChart3 aria-hidden="true" size={14} />Phân tích: {analysisStatusLabel(run)}</StateChip>
                </div>
                <button className="button button--secondary" type="button" disabled={requestState !== 'ready'} onClick={() => void analyzeSymbol(position.symbol)} aria-describedby={`${position.symbol}-analysis-note`}>
                  {analysisActionLabel(requestState)}
                </button>
                <p className="disabled-note" id={`${position.symbol}-analysis-note`}>{note}</p>
              </article>
              );
            })}
          </div>
        )}
        {errorMessage && <p className="form-error" role="alert">{errorMessage}</p>}
      </section>

      {isFormOpen && (
        <section className="form-frame" aria-label="Giao dịch mua mới">
          <div className="form-frame__heading">
            <div>
              <p className="utility-label">Bút toán mới</p>
              <h2>Ghi giao dịch mua</h2>
            </div>
            <button className="text-button" type="button" onClick={closeForm}>Đóng</button>
          </div>
          <form className="transaction-form" noValidate onSubmit={handleSubmit(saveTransaction)}>
            <label>
              <span>Mã chứng khoán</span>
              <input aria-invalid={Boolean(errors.symbol)} aria-label="Mã chứng khoán" placeholder="VNM.VN" {...register('symbol', { required: 'Nhập mã chứng khoán có hậu tố .VN.' })} />
              <small>{errors.symbol?.message ?? 'Mã chứng khoán Việt Nam phải kết thúc bằng .VN.'}</small>
            </label>
            <label>
              <span>Khối lượng</span>
              <input aria-invalid={Boolean(errors.quantity)} aria-label="Khối lượng" inputMode="numeric" min="1" type="number" {...register('quantity', { min: { value: 1, message: 'Khối lượng phải từ 1 trở lên.' }, required: 'Nhập khối lượng.', valueAsNumber: true })} />
              <small>{errors.quantity?.message ?? 'Bản hiện tại chỉ hỗ trợ số cổ phiếu nguyên.'}</small>
            </label>
            <label>
              <span>Đơn giá (VND)</span>
              <input aria-invalid={Boolean(errors.unitPriceVnd)} aria-label="Đơn giá (VND)" inputMode="numeric" min="1" type="number" {...register('unitPriceVnd', { min: { value: 1, message: 'Đơn giá phải lớn hơn 0.' }, required: 'Nhập đơn giá.', valueAsNumber: true })} />
              <small>{errors.unitPriceVnd?.message ?? 'Dùng giá khớp lệnh bằng VND.'}</small>
            </label>
            <label>
              <span>Phí (VND)</span>
              <input aria-invalid={Boolean(errors.feeVnd)} aria-label="Phí (VND)" inputMode="numeric" min="0" type="number" {...register('feeVnd', { min: { value: 0, message: 'Phí không được âm.' }, valueAsNumber: true })} />
              <small>{errors.feeVnd?.message ?? 'Không bắt buộc. Phí được cộng vào giá vốn bình quân.'}</small>
            </label>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            <div className="form-actions">
              <button className="button button--primary" disabled={isMutating} type="submit">Lưu giao dịch</button>
              <button className="button button--secondary" disabled={isMutating} type="button" onClick={closeForm}>Hủy</button>
            </div>
          </form>
        </section>
      )}

    </AppShell>
  );
}
