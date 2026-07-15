import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, jest } from '@jest/globals';

jest.mock('../../lib/supabase/client', () => ({ createSupabaseBrowserClient: jest.fn() }));

import { EmailPasswordForm } from './email-password-form';

describe('EmailPasswordForm', () => {
  it('offers normal sign-in and account registration without a magic-link action', () => {
    render(<EmailPasswordForm />);

    expect(screen.getByRole('button', { name: 'Login' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Register' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  });

  it('shows password confirmation when the user selects registration', () => {
    render(<EmailPasswordForm />);

    fireEvent.click(screen.getByRole('button', { name: 'Register' }));

    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument();
  });
});
