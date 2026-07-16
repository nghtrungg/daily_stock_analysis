import { EmailPasswordForm } from '../../features/auth/email-password-form';

export default function LoginPage() {
  return (
    <main className="auth-shell">
      <section className="auth-intro" aria-labelledby="sign-in-title">
        <div className="brand-lockup" aria-label="Ledger">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span className="brand-copy"><strong>Ledger</strong><small>Personal investing</small></span>
        </div>
        <div>
          <p className="utility-label">Private portfolio access</p>
          <h1 id="sign-in-title">Your investments, kept personal.</h1>
        </div>
        <p className="lead-copy">Track your Vietnam portfolio, watchlist, and analysis history in one owner-only workspace.</p>
        <p className="auth-intro__footer">Vietnam securities · VND · Informational only</p>
      </section>
      <section className="auth-panel" aria-label="Sign in form">
        <div className="auth-panel__heading">
          <h2>Welcome back</h2>
          <p>Sign in or create your private account to continue.</p>
        </div>
        <EmailPasswordForm />
      </section>
    </main>
  );
}
