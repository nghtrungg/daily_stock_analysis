'use client';

import { useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { fromVietnamDateTimeInput, toVietnamDateTimeInput } from '../../lib/datetime';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from './portfolio-provider';

type TradeFields = {
  type: 'buy' | 'sell';
  symbol: string;
  quantity: number;
  unitPriceVnd: number;
  feeVnd: number;
  taxVnd: number;
  occurredAt: string;
};

type TradeFormProps = {
  initialType?: 'buy' | 'sell';
  initialSymbol?: string;
  initialQuantity?: number;
  onClose: () => void;
};

export function TradeForm({ initialType = 'buy', initialSymbol = '', initialQuantity, onClose }: TradeFormProps) {
  const { isMutating, positions, recordTrade, wallet } = usePortfolio();
  const [formError, setFormError] = useState<string | null>(null);
  const { formState: { errors }, handleSubmit, register, watch } = useForm<TradeFields>({
    defaultValues: {
      type: initialType,
      symbol: initialSymbol,
      quantity: initialQuantity,
      unitPriceVnd: undefined,
      feeVnd: 0,
      taxVnd: 0,
      occurredAt: toVietnamDateTimeInput()
    }
  });
  const [type, symbol, quantity, unitPriceVnd, feeVnd, taxVnd] = watch(['type', 'symbol', 'quantity', 'unitPriceVnd', 'feeVnd', 'taxVnd']);
  const heldQuantity = positions.find((position) => position.symbol === symbol.trim().toUpperCase())?.quantity ?? 0;
  const preview = useMemo(() => {
    const principal = Number.isFinite(quantity) && Number.isFinite(unitPriceVnd) ? Math.round(quantity * unitPriceVnd) : 0;
    const fee = Number.isFinite(feeVnd) ? feeVnd : 0;
    const tax = Number.isFinite(taxVnd) ? taxVnd : 0;
    if (type === 'sell') {
      const net = principal - fee - tax;
      return { amount: net, text: `Thu ròng ${formatVnd(net)} · Sau bán còn tối đa ${Math.max(heldQuantity - (Number.isFinite(quantity) ? quantity : 0), 0)} cổ phiếu` };
    }
    const cost = principal + fee;
    return { amount: -cost, text: `Tổng chi ${formatVnd(cost)} · Số dư dự kiến ${formatVnd(wallet.availableCashVnd - cost)}` };
  }, [feeVnd, heldQuantity, quantity, taxVnd, type, unitPriceVnd, wallet.availableCashVnd]);

  async function submit(fields: TradeFields) {
    setFormError(null);
    try {
      await recordTrade({
        ...fields,
        occurredAt: fromVietnamDateTimeInput(fields.occurredAt),
        taxVnd: fields.type === 'sell' ? fields.taxVnd : 0
      });
      onClose();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Không thể lưu giao dịch.');
    }
  }

  return (
    <section className="form-frame trade-sheet" role="dialog" aria-modal="true" aria-labelledby="trade-form-title">
      <div className="form-frame__heading">
        <div><p className="utility-label">Bút toán giao dịch</p><h2 id="trade-form-title">Ghi giao dịch mua hoặc bán</h2></div>
        <button className="text-button" disabled={isMutating} type="button" onClick={onClose}>Đóng</button>
      </div>
      <form className="transaction-form" noValidate onSubmit={handleSubmit(submit)}>
        <fieldset className="choice-fieldset">
          <legend>Loại giao dịch</legend>
          <label><input type="radio" value="buy" {...register('type')} /> Mua</label>
          <label><input type="radio" value="sell" {...register('type')} /> Bán</label>
        </fieldset>
        <label>
          <span>Mã chứng khoán</span>
          <input aria-invalid={Boolean(errors.symbol)} aria-label="Mã chứng khoán" placeholder="VNM.VN" {...register('symbol', { required: 'Nhập mã chứng khoán có hậu tố .VN.' })} />
          <small>{errors.symbol?.message ?? 'Chỉ hỗ trợ mã chứng khoán Việt Nam có hậu tố .VN.'}</small>
        </label>
        <label>
          <span>Khối lượng</span>
          <input aria-invalid={Boolean(errors.quantity)} aria-label="Khối lượng" inputMode="decimal" min="0.0001" step="0.0001" type="number" {...register('quantity', {
            required: 'Nhập khối lượng.', min: { value: 0.0001, message: 'Khối lượng phải lớn hơn 0.' },
            validate: (value) => Math.abs(Math.round(value * 10000) - value * 10000) < 1e-8 || 'Tối đa 4 chữ số thập phân.', valueAsNumber: true
          })} />
          <small>{errors.quantity?.message ?? (type === 'sell' ? `Đang nắm giữ ${heldQuantity} cổ phiếu.` : 'Cho phép tối đa 4 chữ số thập phân.')}</small>
        </label>
        <label>
          <span>Đơn giá (VND)</span>
          <input aria-invalid={Boolean(errors.unitPriceVnd)} aria-label="Đơn giá (VND)" inputMode="numeric" min="1" step="1" type="number" {...register('unitPriceVnd', {
            required: 'Nhập đơn giá.', min: { value: 1, message: 'Đơn giá phải lớn hơn 0.' },
            validate: (value) => Number.isSafeInteger(value) || 'Đơn giá phải là số VND nguyên.', valueAsNumber: true
          })} />
          <small>{errors.unitPriceVnd?.message ?? 'Dùng giá khớp lệnh thực tế bằng VND.'}</small>
        </label>
        <label>
          <span>Phí (VND)</span>
          <input aria-invalid={Boolean(errors.feeVnd)} aria-label="Phí (VND)" inputMode="numeric" min="0" step="1" type="number" {...register('feeVnd', {
            min: { value: 0, message: 'Phí không được âm.' }, validate: (value) => Number.isSafeInteger(value) || 'Phí phải là số VND nguyên.', valueAsNumber: true
          })} />
          <small>{errors.feeVnd?.message ?? (type === 'buy' ? 'Phí mua được cộng vào giá vốn.' : 'Phí bán được trừ khỏi tiền thu ròng.')}</small>
        </label>
        {type === 'sell' && <label>
          <span>Thuế (VND)</span>
          <input aria-invalid={Boolean(errors.taxVnd)} aria-label="Thuế (VND)" inputMode="numeric" min="0" step="1" type="number" {...register('taxVnd', {
            min: { value: 0, message: 'Thuế không được âm.' }, validate: (value) => Number.isSafeInteger(value) || 'Thuế phải là số VND nguyên.', valueAsNumber: true
          })} />
          <small>{errors.taxVnd?.message ?? 'Thuế bán được trừ khỏi tiền thu ròng.'}</small>
        </label>}
        <label>
          <span>Thời điểm</span>
          <input aria-invalid={Boolean(errors.occurredAt)} aria-label="Thời điểm giao dịch" type="datetime-local" {...register('occurredAt', { required: 'Chọn thời điểm giao dịch.' })} />
          <small>{errors.occurredAt?.message ?? 'Giờ Việt Nam (ICT).'}</small>
        </label>
        <aside className={`accounting-preview${preview.amount < 0 && wallet.availableCashVnd + preview.amount < 0 ? ' accounting-preview--warning' : ''}`} aria-live="polite">
          <strong>{type === 'buy' ? 'Xem trước giao dịch mua' : 'Xem trước giao dịch bán'}</strong>
          <span>{preview.text}</span>
        </aside>
        {formError && <p className="form-error" role="alert">{formError}</p>}
        <div className="form-actions">
          <button className="button button--primary" disabled={isMutating} type="submit">{isMutating ? 'Đang lưu…' : type === 'buy' ? 'Ghi giao dịch mua' : 'Ghi giao dịch bán'}</button>
          <button className="button button--secondary" disabled={isMutating} type="button" onClick={onClose}>Hủy</button>
        </div>
      </form>
    </section>
  );
}
