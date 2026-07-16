import { EmailPasswordForm } from '../../features/auth/email-password-form';

export default function LoginPage() {
  return (
    <main className="auth-shell">
      <section className="auth-intro" aria-labelledby="sign-in-title">
        <div className="brand-lockup" aria-label="Ledger">
          <span className="brand-mark" aria-hidden="true">L</span>
          <span className="brand-copy"><strong>Ledger</strong><small>Đầu tư cá nhân</small></span>
        </div>
        <div>
          <p className="utility-label">Truy cập danh mục riêng tư</p>
          <h1 id="sign-in-title">Khoản đầu tư của bạn, luôn riêng tư.</h1>
        </div>
        <p className="lead-copy">Theo dõi danh mục Việt Nam, danh sách quan tâm và lịch sử phân tích trong không gian chỉ dành cho bạn.</p>
        <p className="auth-intro__footer">Chứng khoán Việt Nam · VND · Chỉ mang tính tham khảo</p>
      </section>
      <section className="auth-panel" aria-label="Biểu mẫu đăng nhập">
        <div className="auth-panel__heading">
          <h2>Chào mừng bạn trở lại</h2>
          <p>Đăng nhập hoặc tạo tài khoản riêng tư để tiếp tục.</p>
        </div>
        <EmailPasswordForm />
      </section>
    </main>
  );
}
