'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { ArrowDownToLine, ArrowUpFromLine, WalletCards } from 'lucide-react';
import { fromVietnamDateTimeInput, toVietnamDateTimeInput } from '../../lib/datetime';
import { formatVnd } from '../../lib/money';
import { usePortfolio } from './portfolio-provider';

type WalletFields = {
  type: 'deposit' | 'withdrawal';
  amountVnd: number;
  occurredAt: string;
  note: string;
};

export function WalletForm() {
  const { isMutating, recordCashEntry, wallet } = usePortfolio();
  const [formMessage, setFormMessage] = useState<{ tone: 'error' | 'success'; text: string } | null>(null);
  const { formState: { errors }, handleSubmit, register, reset, watch } = useForm<WalletFields>({
    defaultValues: { type: 'deposit', amountVnd: undefined, occurredAt: toVietnamDateTimeInput(), note: '' }
  });
  const amountVnd = watch('amountVnd');

  async function submit(fields: WalletFields) {
    setFormMessage(null);
    try {
      await recordCashEntry({
        type: fields.type,
        amountVnd: fields.amountVnd,
        occurredAt: fromVietnamDateTimeInput(fields.occurredAt),
        note: fields.note
      });
      setFormMessage({ tone: 'success', text: fields.type === 'deposit' ? 'Đã ghi nhận khoản nạp tiền.' : 'Đã ghi nhận khoản rút tiền.' });
      reset({ ...fields, amountVnd: undefined, occurredAt: toVietnamDateTimeInput(), note: '' });
    } catch (error) {
      setFormMessage({ tone: 'error', text: error instanceof Error ? error.message : 'Không thể cập nhật ví.' });
    }
  }

  return (
    <section className="wallet-panel" aria-labelledby="wallet-title">
      <div className="wallet-panel__balance">
        <div className="empty-frame__mark" aria-hidden="true"><WalletCards size={26} /></div>
        <div>
          <p className="utility-label">Ví ghi sổ · VND</p>
          <h2 id="wallet-title">Số dư khả dụng</h2>
          <strong>{formatVnd(wallet.availableCashVnd)}</strong>
          <p>{wallet.availableCashVnd === 0 ? 'Hãy nạp tiền vào sổ trước khi ghi giao dịch mua.' : 'Đây là số dư ghi sổ, không phải tiền trong tài khoản ngân hàng.'}</p>
        </div>
      </div>

      <form className="transaction-form wallet-panel__form" noValidate onSubmit={handleSubmit(submit)}>
        <fieldset className="choice-fieldset">
          <legend>Loại bút toán</legend>
          <label><input type="radio" value="deposit" {...register('type')} /><ArrowDownToLine aria-hidden="true" size={16} /> Nạp tiền</label>
          <label><input type="radio" value="withdrawal" {...register('type')} /><ArrowUpFromLine aria-hidden="true" size={16} /> Rút tiền</label>
        </fieldset>
        <label>
          <span>Số tiền (VND)</span>
          <input aria-invalid={Boolean(errors.amountVnd)} aria-label="Số tiền (VND)" inputMode="numeric" min="1" step="1" type="number" {...register('amountVnd', {
            required: 'Nhập số tiền.',
            min: { value: 1, message: 'Số tiền phải lớn hơn 0.' },
            validate: (value) => Number.isSafeInteger(value) || 'Số tiền phải là số VND nguyên.',
            valueAsNumber: true
          })} />
          <small>{errors.amountVnd?.message ?? (Number.isFinite(amountVnd) ? formatVnd(amountVnd) : 'Chỉ nhập số VND nguyên, không nhập số âm.')}</small>
        </label>
        <label>
          <span>Thời điểm</span>
          <input aria-invalid={Boolean(errors.occurredAt)} aria-label="Thời điểm bút toán ví" type="datetime-local" {...register('occurredAt', { required: 'Chọn thời điểm.' })} />
          <small>{errors.occurredAt?.message ?? 'Giờ Việt Nam (ICT).'}</small>
        </label>
        <label>
          <span>Ghi chú</span>
          <input aria-label="Ghi chú ví" maxLength={500} placeholder="Ví dụ: Vốn đầu tư tháng 7" {...register('note', { maxLength: { value: 500, message: 'Ghi chú không được vượt quá 500 ký tự.' } })} />
          <small>{errors.note?.message ?? 'Không bắt buộc.'}</small>
        </label>
        {formMessage && <p className={`form-${formMessage.tone}`} role={formMessage.tone === 'error' ? 'alert' : 'status'}>{formMessage.text}</p>}
        <div className="form-actions">
          <button className="button button--secondary" disabled={isMutating} type="submit">{isMutating ? 'Đang lưu…' : 'Ghi bút toán ví'}</button>
        </div>
      </form>
    </section>
  );
}
