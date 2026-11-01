import React, { useState } from 'react';
import {
  Cloud, Mail, ArrowRight, ShieldCheck, AlertCircle, CheckCircle,
  Sun, Moon, ChevronLeft
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const ForgotPasswordPage = ({ onNavigate }) => {
  const { theme, toggleTheme } = useTheme();
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [serverMsg, setServerMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');
    if (!email.trim()) {
      setErrorMsg('Please enter your email address.');
      return;
    }
    if (!EMAIL_REGEX.test(email.trim())) {
      setErrorMsg('Please enter a valid email address.');
      return;
    }

    setSubmitting(true);
    try {
      const res = await api.post('/auth/password-reset/', { email: email.trim().toLowerCase() });
      setServerMsg(res.data?.detail || 'Password reset instructions have been dispatched if the account exists.');
      setSubmitted(true);
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to request password reset. Please try again later.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-page">
      {/* Theme toggle top-right */}
      <button
        onClick={toggleTheme}
        className="navbar-icon-btn"
        title="Toggle theme"
        style={{ position: 'fixed', top: 20, right: 20 }}
      >
        {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
      </button>

      {/* Back to Login */}
      <button
        className="btn btn-ghost"
        onClick={() => onNavigate('login')}
        style={{ position: 'fixed', top: 20, left: 20, gap: 6, fontSize: '0.85rem' }}
      >
        <ChevronLeft size={16} /> Back to Sign In
      </button>

      <div className="auth-card">
        {/* Brand */}
        <div className="auth-logo">
          <Cloud size={30} color="#fff" />
        </div>
        <h1 className="auth-title">Reset Password</h1>
        <p className="auth-subtitle">Enter your email to receive recovery instructions</p>

        {errorMsg && (
          <div className="alert-error" style={{ marginBottom: 16 }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            {errorMsg}
          </div>
        )}

        {submitted ? (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%',
              background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px'
            }}>
              <CheckCircle size={28} color="var(--accent-emerald)" />
            </div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 8 }}>Request Submitted</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: 20 }}>
              {serverMsg}
            </p>
            <button
              className="btn btn-secondary"
              onClick={() => onNavigate('login')}
              style={{ width: '100%', padding: '12px' }}
            >
              Return to Sign In
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate>
            <div className="form-group">
              <label className="form-label" htmlFor="reset-email">Account Email</label>
              <div className="input-wrapper">
                <Mail size={17} className="input-icon-left" />
                <input
                  id="reset-email"
                  type="email"
                  className="input-field has-icon-left"
                  placeholder="user@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  maxLength={254}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
              style={{ width: '100%', padding: '13px', fontSize: '1rem', borderRadius: 10, marginTop: 10 }}
            >
              {submitting ? 'Sending Request...' : (
                <>
                  Send Reset Link
                  <ArrowRight size={18} />
                </>
              )}
            </button>
          </form>
        )}

        <div style={{ textAlign: 'center', marginTop: 28, fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
          <ShieldCheck size={13} color="var(--accent-emerald)" />
          VaultCloud Secure Account Recovery
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
