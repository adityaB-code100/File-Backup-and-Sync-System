import React, { useState } from 'react';
import {
  Cloud, Mail, Lock, ArrowRight, ShieldCheck, AlertCircle, CheckCircle,
  Sun, Moon, ChevronLeft, KeyRound, Eye, EyeOff
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import api from '../services/api';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const ForgotPasswordPage = ({ onNavigate }) => {
  const { theme, toggleTheme } = useTheme();
  const [step, setStep] = useState('request'); // 'request' | 'confirm' | 'success'

  // Request form state
  const [email, setEmail] = useState('');
  const [submittingReq, setSubmittingReq] = useState(false);

  // Confirm form state
  const [verificationCode, setVerificationCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submittingConfirm, setSubmittingConfirm] = useState(false);

  // Status messages
  const [serverMsg, setServerMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const handleRequestSubmit = async (e) => {
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

    setSubmittingReq(true);
    try {
      const res = await api.post('/auth/password-reset/', { email: email.trim().toLowerCase() });
      setServerMsg(res.data?.detail || 'If an account exists, password reset instructions have been dispatched.');
      // The verification code is delivered strictly via email and must start empty for user entry
      setVerificationCode('');
      setStep('confirm');
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to request password reset. Please try again.');
    } finally {
      setSubmittingReq(false);
    }
  };

  const handleConfirmSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!verificationCode.trim()) {
      setErrorMsg('Please enter the 6-digit verification code from your email.');
      return;
    }
    if (verificationCode.trim().length !== 6) {
      setErrorMsg('Verification code must be exactly 6 digits.');
      return;
    }
    if (!newPassword) {
      setErrorMsg('Please enter your new password.');
      return;
    }
    if (newPassword.length < 8) {
      setErrorMsg('New password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMsg('Passwords do not match.');
      return;
    }
    const emailLower = email.trim().toLowerCase();
    const emailLocal = emailLower.split('@')[0];
    if (newPassword.toLowerCase() === emailLower || (emailLocal && newPassword.toLowerCase() === emailLocal)) {
      setErrorMsg('Password cannot be the same as your email address.');
      return;
    }

    setSubmittingConfirm(true);
    try {
      const res = await api.post('/auth/password-reset/confirm/', {
        token: verificationCode.trim(),
        email: emailLower,
        new_password: newPassword,
      });
      setServerMsg(res.data?.detail || 'Password successfully reset.');
      setStep('success');
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to reset password. The code may be expired or invalid.');
    } finally {
      setSubmittingConfirm(false);
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
        <h1 className="auth-title">
          {step === 'confirm' ? 'Set New Password' : step === 'success' ? 'Password Reset' : 'Reset Password'}
        </h1>
        <p className="auth-subtitle">
          {step === 'confirm'
            ? 'Enter the 6-digit code from your email and choose a new password'
            : step === 'success'
            ? 'Your credentials have been securely updated'
            : 'Enter your email to receive recovery instructions'}
        </p>

        {errorMsg && (
          <div className="alert-error" style={{ marginBottom: 16 }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            {errorMsg}
          </div>
        )}

        {serverMsg && step === 'confirm' && (
          <div style={{
            padding: '10px 14px', borderRadius: 'var(--radius-sm)',
            background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)',
            marginBottom: 16, fontSize: '0.82rem', color: 'var(--primary)'
          }}>
            {serverMsg}
          </div>
        )}

        {/* STEP 1: REQUEST TOKEN */}
        {step === 'request' && (
          <form onSubmit={handleRequestSubmit} noValidate>
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
              disabled={submittingReq}
              style={{ width: '100%', padding: '13px', fontSize: '1rem', borderRadius: 10, marginTop: 10 }}
            >
              {submittingReq ? 'Sending Request...' : (
                <>
                  Send Reset Token
                  <ArrowRight size={18} />
                </>
              )}
            </button>

            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <button
                type="button"
                onClick={() => setStep('confirm')}
                style={{ background: 'none', border: 'none', color: 'var(--primary)', fontSize: '0.82rem', cursor: 'pointer', fontWeight: 600 }}
              >
                Already have a verification code? Enter it here
              </button>
            </div>
          </form>
        )}

        {/* STEP 2: ENTER TOKEN AND NEW PASSWORD */}
        {step === 'confirm' && (
          <form onSubmit={handleConfirmSubmit} noValidate>
            {email && (
              <div style={{
                marginBottom: 16,
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg-card-subtle, rgba(255,255,255,0.04))',
                border: '1px solid var(--border-color)',
                fontSize: '0.82rem',
                color: 'var(--text-muted)'
              }}>
                Registered email: <strong style={{ color: 'var(--text-main, #ffffff)' }}>{email}</strong>
              </div>
            )}

            <div className="form-group">
              <label className="form-label" htmlFor="verification-code">Verification Code</label>
              <div className="input-wrapper">
                <KeyRound size={17} className="input-icon-left" />
                <input
                  id="verification-code"
                  type="text"
                  value={verificationCode}
                  onChange={(e) =>
                    setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))
                  }
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={6}
                  placeholder="Enter 6-digit verification code"
                  className="input-field has-icon-left"
                  aria-label="6-digit verification code"
                />
              </div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
                Check your inbox for a 6-digit verification code.
              </span>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="new-password">New Password</label>
              <div className="input-wrapper">
                <Lock size={17} className="input-icon-left" />
                <input
                  id="new-password"
                  type={showPassword ? 'text' : 'password'}
                  className="input-field has-icon-left has-icon-right"
                  placeholder="At least 8 characters"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  maxLength={128}
                />
                <span
                  className="input-icon-right"
                  onClick={() => setShowPassword(!showPassword)}
                  role="button"
                  tabIndex={0}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </span>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="confirm-password">Confirm New Password</label>
              <div className="input-wrapper">
                <Lock size={17} className="input-icon-left" />
                <input
                  id="confirm-password"
                  type={showPassword ? 'text' : 'password'}
                  className="input-field has-icon-left"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  maxLength={128}
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submittingConfirm}
              style={{ width: '100%', padding: '13px', fontSize: '1rem', borderRadius: 10, marginTop: 10 }}
            >
              {submittingConfirm ? 'Updating Password...' : (
                <>
                  Change Password
                  <ArrowRight size={18} />
                </>
              )}
            </button>

            <div style={{ textAlign: 'center', marginTop: 16 }}>
              <button
                type="button"
                onClick={() => { setVerificationCode(''); setStep('request'); }}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', fontSize: '0.82rem', cursor: 'pointer' }}
              >
                ← Request a new token
              </button>
            </div>
          </form>
        )}

        {/* STEP 3: SUCCESS */}
        {step === 'success' && (
          <div style={{ textAlign: 'center', padding: '16px 0' }}>
            <div style={{
              width: 52, height: 52, borderRadius: '50%',
              background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px'
            }}>
              <CheckCircle size={28} color="var(--accent-emerald)" />
            </div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 8 }}>Password Reset Complete</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: 20 }}>
              Your password has been securely updated. You can now log in using your new credentials.
            </p>
            <button
              className="btn btn-primary"
              onClick={() => onNavigate('login')}
              style={{ width: '100%', padding: '12px' }}
            >
              Sign In to Your Account
            </button>
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: 28, fontSize: '0.75rem', color: 'var(--text-dim)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
          <ShieldCheck size={13} color="var(--accent-emerald)" />
          VaultCloud Argon2 Encrypted Account Security
        </div>
      </div>
    </div>
  );
};

export default ForgotPasswordPage;
