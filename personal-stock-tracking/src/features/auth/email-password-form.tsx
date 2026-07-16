'use client';

import { useState, type FormEvent } from 'react';
import { createSupabaseBrowserClient } from '../../lib/supabase/client';

type AuthMode = 'sign-in' | 'sign-up';

export function EmailPasswordForm() {
  const [mode, setMode] = useState<AuthMode>('sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const isSignUp = mode === 'sign-up';

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (isSignUp && password !== confirmation) {
      setError('Mật khẩu xác nhận không khớp.');
      return;
    }

    setIsPending(true);
    const supabase = createSupabaseBrowserClient();

    if (isSignUp) {
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/auth/confirm` }
      });

      setIsPending(false);
      if (signUpError) {
        setError('Không thể tạo tài khoản. Vui lòng kiểm tra thông tin và thử lại.');
        return;
      }
      if (!data.session) {
        setMessage('Hãy kiểm tra email để xác nhận tài khoản, sau đó đăng nhập bằng mật khẩu.');
        return;
      }
    } else {
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });

      setIsPending(false);
      if (signInError) {
        setError('Email hoặc mật khẩu không đúng.');
        return;
      }
    }

    window.location.assign('/');
  }

  return (
    <form className="transaction-form auth-form" noValidate onSubmit={(event) => void submit(event)}>
      <div className="auth-mode" role="group" aria-label="Thao tác tài khoản">
        <button className={mode === 'sign-in' ? 'button button--primary' : 'button button--secondary'} onClick={() => setMode('sign-in')} type="button">Đăng nhập</button>
        <button className={mode === 'sign-up' ? 'button button--primary' : 'button button--secondary'} onClick={() => setMode('sign-up')} type="button">Đăng ký</button>
      </div>
      <label htmlFor="auth-email">
        <span>Địa chỉ email</span>
        <input aria-label="Địa chỉ email" autoComplete="email" id="auth-email" inputMode="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
        <small>Dùng địa chỉ email sở hữu danh mục riêng tư này.</small>
      </label>
      <label htmlFor="auth-password">
        <span>Mật khẩu</span>
        <input aria-describedby="password-help" aria-label="Mật khẩu" autoComplete={isSignUp ? 'new-password' : 'current-password'} id="auth-password" minLength={12} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
        <small id="password-help">Dùng ít nhất 12 ký tự.</small>
      </label>
      {isSignUp && (
        <label htmlFor="auth-password-confirmation">
          <span>Xác nhận mật khẩu</span>
          <input aria-label="Xác nhận mật khẩu" autoComplete="new-password" id="auth-password-confirmation" minLength={12} onChange={(event) => setConfirmation(event.target.value)} required type="password" value={confirmation} />
        </label>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      {message && <p className="form-success" role="status">{message}</p>}
      <div className="form-actions">
        <button className="button button--primary" disabled={isPending} type="submit">{isPending ? 'Đang xử lý…' : isSignUp ? 'Tạo tài khoản' : 'Đăng nhập tài khoản'}</button>
      </div>
    </form>
  );
}
