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
      setError('Passwords do not match.');
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
        setError('Account creation could not be completed. Check your details and try again.');
        return;
      }
      if (!data.session) {
        setMessage('Check your email to confirm the account, then sign in with your password.');
        return;
      }
    } else {
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });

      setIsPending(false);
      if (signInError) {
        setError('Email or password is incorrect.');
        return;
      }
    }

    window.location.assign('/');
  }

  return (
    <form className="transaction-form auth-form" noValidate onSubmit={(event) => void submit(event)}>
      <div className="auth-mode" role="group" aria-label="Account action">
        <button className={mode === 'sign-in' ? 'button button--primary' : 'button button--secondary'} onClick={() => setMode('sign-in')} type="button">Login</button>
        <button className={mode === 'sign-up' ? 'button button--primary' : 'button button--secondary'} onClick={() => setMode('sign-up')} type="button">Register</button>
      </div>
      <label htmlFor="auth-email">
        <span>Email address</span>
        <input aria-label="Email address" autoComplete="email" id="auth-email" inputMode="email" onChange={(event) => setEmail(event.target.value)} required type="email" value={email} />
        <small>Use the email address that owns this private portfolio.</small>
      </label>
      <label htmlFor="auth-password">
        <span>Password</span>
        <input aria-describedby="password-help" aria-label="Password" autoComplete={isSignUp ? 'new-password' : 'current-password'} id="auth-password" minLength={12} onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
        <small id="password-help">Use at least 12 characters.</small>
      </label>
      {isSignUp && (
        <label htmlFor="auth-password-confirmation">
          <span>Confirm password</span>
          <input aria-label="Confirm password" autoComplete="new-password" id="auth-password-confirmation" minLength={12} onChange={(event) => setConfirmation(event.target.value)} required type="password" value={confirmation} />
        </label>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      {message && <p className="form-success" role="status">{message}</p>}
      <div className="form-actions">
        <button className="button button--primary" disabled={isPending} type="submit">{isPending ? 'Working…' : isSignUp ? 'Create account' : 'Sign in'}</button>
      </div>
    </form>
  );
}
