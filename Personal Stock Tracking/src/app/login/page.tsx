import { EmailPasswordForm } from '../../features/auth/email-password-form';

export default function LoginPage() {
  return (
    <main className="app-shell">
      <header className="app-header"><span className="wordmark">Ledger</span></header>
      <section className="portfolio-lead" aria-labelledby="sign-in-title">
        <div>
          <p className="utility-label">Private portfolio access</p>
          <h1 id="sign-in-title">Private sign in</h1>
        </div>
        <p className="lead-copy">Sign in with your email and password to access your own Vietnam portfolio, watchlist, and analysis history.</p>
      </section>
      <section className="workbench" aria-label="Sign in form"><EmailPasswordForm /></section>
      <footer className="app-footer"><p>Ledger · Vietnam portfolio tracking · Informational only</p><p>All values in VND</p></footer>
    </main>
  );
}
