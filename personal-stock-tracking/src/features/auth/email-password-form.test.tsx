import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';

jest.mock('../../lib/supabase/client', () => ({ createSupabaseBrowserClient: jest.fn() }));

import { EmailPasswordForm } from './email-password-form';

describe('EmailPasswordForm', () => {
  it('offers normal sign-in and account registration without a magic-link action', () => {
    render(<EmailPasswordForm />);

    expect(screen.getByRole('button', { name: 'Đăng nhập' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Đăng ký' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Đăng nhập tài khoản' })).toBeInTheDocument();
    expect(screen.getByLabelText('Mật khẩu')).toHaveAttribute('type', 'password');
  });

  it('shows password confirmation when the user selects registration', () => {
    render(<EmailPasswordForm />);

    fireEvent.click(screen.getByRole('button', { name: 'Đăng ký' }));

    expect(screen.getByLabelText('Xác nhận mật khẩu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Tạo tài khoản' })).toBeInTheDocument();
  });
});
