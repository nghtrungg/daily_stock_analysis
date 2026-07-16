'use client';

import { useState, type FormEvent } from 'react';
import { Trash2 } from 'lucide-react';
import { fromVietnamDateTimeInput, toVietnamDateTimeInput } from '../../lib/datetime';
import { usePortfolio } from '../portfolio/portfolio-provider';
import { ledgerItemLabel, type ActivityLedgerItem } from './ledger-entry-row';

export function LedgerEntryEditor({ item, onClose }: { item: ActivityLedgerItem; onClose: () => void }) {
  const { deleteCashEntry, deleteTrade, isMutating, updateCashEntry, updateTrade } = usePortfolio();
  const [type, setType] = useState(item.kind === 'cash' ? item.entry.type : item.entry.type);
  const [amountVnd, setAmountVnd] = useState(item.kind === 'cash' ? item.entry.amountVnd : 0);
  const [note, setNote] = useState(item.kind === 'cash' ? item.entry.note ?? '' : '');
  const [symbol, setSymbol] = useState(item.kind === 'trade' ? item.entry.symbol : '');
  const [quantity, setQuantity] = useState(item.kind === 'trade' ? item.entry.quantity : 0);
  const [unitPriceVnd, setUnitPriceVnd] = useState(item.kind === 'trade' ? item.entry.unitPriceVnd : 0);
  const [feeVnd, setFeeVnd] = useState(item.kind === 'trade' ? item.entry.feeVnd : 0);
  const [taxVnd, setTaxVnd] = useState(item.kind === 'trade' ? item.entry.taxVnd : 0);
  const [occurredAt, setOccurredAt] = useState(toVietnamDateTimeInput(item.entry.occurredAt));
  const [formError, setFormError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    try {
      if (item.kind === 'cash') {
        await updateCashEntry({
          id: item.entry.id,
          expectedUpdatedAt: item.entry.updatedAt,
          type: type as 'deposit' | 'withdrawal',
          amountVnd,
          note,
          occurredAt: fromVietnamDateTimeInput(occurredAt)
        });
      } else {
        await updateTrade({
          id: item.entry.id,
          expectedUpdatedAt: item.entry.updatedAt,
          type: type as 'buy' | 'sell',
          symbol,
          quantity,
          unitPriceVnd,
          feeVnd,
          taxVnd: type === 'sell' ? taxVnd : 0,
          occurredAt: fromVietnamDateTimeInput(occurredAt)
        });
      }
      onClose();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Không thể chỉnh sửa bút toán.');
    }
  }

  async function remove() {
    const confirmed = window.confirm(`Xóa bút toán ${ledgerItemLabel(item)} này? Ví, khoản nắm giữ và các giá trị về sau sẽ được tính lại.`);
    if (!confirmed) return;
    setFormError(null);
    try {
      if (item.kind === 'cash') await deleteCashEntry({ id: item.entry.id, updatedAt: item.entry.updatedAt });
      else await deleteTrade({ id: item.entry.id, updatedAt: item.entry.updatedAt });
      onClose();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Không thể xóa bút toán.');
    }
  }

  return (
    <section className="form-frame ledger-editor" role="dialog" aria-modal="true" aria-labelledby="ledger-editor-title">
      <div className="form-frame__heading">
        <div><p className="utility-label">Sửa lỗi ghi sổ</p><h2 id="ledger-editor-title">Chỉnh sửa {ledgerItemLabel(item).toLocaleLowerCase('vi-VN')}</h2></div>
        <button className="text-button" disabled={isMutating} type="button" onClick={onClose}>Đóng</button>
      </div>
      <p className="ledger-editor__warning">Thay đổi này có thể tính lại số dư ví, vị thế và lãi/lỗ của mọi bút toán về sau. Máy chủ sẽ từ chối nếu lịch sử trở nên âm tiền hoặc âm cổ phiếu.</p>
      <form className="transaction-form" onSubmit={submit}>
        <label>
          <span>Loại bút toán</span>
          <select aria-label="Loại bút toán" value={type} onChange={(event) => setType(event.target.value as typeof type)}>
            {item.kind === 'cash' ? <><option value="deposit">Nạp tiền</option><option value="withdrawal">Rút tiền</option></> : <><option value="buy">Mua</option><option value="sell">Bán</option></>}
          </select>
        </label>
        {item.kind === 'cash' ? <>
          <label><span>Số tiền (VND)</span><input aria-label="Số tiền (VND)" min="1" step="1" type="number" value={amountVnd} onChange={(event) => setAmountVnd(event.target.valueAsNumber)} /></label>
          <label><span>Ghi chú</span><input aria-label="Ghi chú" maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} /></label>
        </> : <>
          <label><span>Mã chứng khoán</span><input aria-label="Mã chứng khoán" value={symbol} onChange={(event) => setSymbol(event.target.value)} /></label>
          <label><span>Khối lượng</span><input aria-label="Khối lượng" min="0.0001" step="0.0001" type="number" value={quantity} onChange={(event) => setQuantity(event.target.valueAsNumber)} /></label>
          <label><span>Đơn giá (VND)</span><input aria-label="Đơn giá (VND)" min="1" step="1" type="number" value={unitPriceVnd} onChange={(event) => setUnitPriceVnd(event.target.valueAsNumber)} /></label>
          <label><span>Phí (VND)</span><input aria-label="Phí (VND)" min="0" step="1" type="number" value={feeVnd} onChange={(event) => setFeeVnd(event.target.valueAsNumber)} /></label>
          {type === 'sell' && <label><span>Thuế (VND)</span><input aria-label="Thuế (VND)" min="0" step="1" type="number" value={taxVnd} onChange={(event) => setTaxVnd(event.target.valueAsNumber)} /></label>}
        </>}
        <label><span>Thời điểm</span><input aria-label="Thời điểm bút toán" type="datetime-local" value={occurredAt} onChange={(event) => setOccurredAt(event.target.value)} /></label>
        {formError && <p className="form-error" role="alert">{formError}</p>}
        <div className="form-actions ledger-editor__actions">
          <button className="button button--primary" disabled={isMutating} type="submit">{isMutating ? 'Đang lưu…' : 'Lưu chỉnh sửa'}</button>
          <button className="button button--secondary" disabled={isMutating} type="button" onClick={onClose}>Hủy</button>
          <button className="button button--danger" disabled={isMutating} type="button" onClick={() => void remove()}><Trash2 aria-hidden="true" size={16} />Xóa bút toán</button>
        </div>
      </form>
    </section>
  );
}
