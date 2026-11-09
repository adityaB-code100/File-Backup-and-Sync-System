import React, { useState, useEffect, useRef } from 'react';
import { ShieldCheck, Mail, Smartphone, AlertCircle, CheckCircle, RefreshCw, X, ArrowRight } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const OTPVerificationModal = ({
  isOpen,
  onClose,
  recipient,
  channel = 'email', // 'email' | 'sms'
  purpose = 'registration',
  onSuccess,
  title,
  subtitle,
}) => {
  const { verifyEmailOTP, verifyMobileOTP, resendOTP, sendMobileOTP } = useAuth();

  const [digits, setDigits] = useState(['', '', '', '', '', '']);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [cooldown, setCooldown] = useState(60);

  const inputRefs = useRef([]);

  // Auto-focus first input when modal opens
  useEffect(() => {
    if (isOpen) {
      setDigits(['', '', '', '', '', '']);
      setErrorMsg('');
      setSuccessMsg('');
      setCooldown(60);
      setTimeout(() => {
        if (inputRefs.current[0]) {
          inputRefs.current[0].focus();
        }
      }, 100);
    }
  }, [isOpen]);

  // Countdown timer for resend
  useEffect(() => {
    let timer;
    if (isOpen && cooldown > 0) {
      timer = setInterval(() => {
        setCooldown((prev) => (prev > 0 ? prev - 1 : 0));
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [isOpen, cooldown]);

  if (!isOpen) return null;

  const handleChange = (index, value) => {
    setErrorMsg('');
    const char = value.slice(-1); // take only the last character
    if (char && !/^\d$/.test(char)) return; // numbers only

    const newDigits = [...digits];
    newDigits[index] = char;
    setDigits(newDigits);

    // Auto-advance to next input
    if (char && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text').trim();
    if (/^\d{6}$/.test(pasted)) {
      const split = pasted.split('');
      setDigits(split);
      inputRefs.current[5]?.focus();
    }
  };

  const handleSubmit = async (e) => {
    if (e) e.preventDefault();
    setErrorMsg('');
    setSuccessMsg('');

    const otpCode = digits.join('');
    if (otpCode.length !== 6) {
      setErrorMsg('Please enter all 6 digits.');
      return;
    }

    setSubmitting(true);
    try {
      let data;
      if (channel === 'email') {
        data = await verifyEmailOTP(recipient, otpCode, purpose);
      } else {
        data = await verifyMobileOTP(otpCode);
      }

      setSuccessMsg('Verification successful!');
      setTimeout(() => {
        if (onSuccess) onSuccess(data);
        if (onClose) onClose();
      }, 700);
    } catch (err) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        'Verification failed. Please check your code.';
      setErrorMsg(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (cooldown > 0 || resending) return;
    setErrorMsg('');
    setSuccessMsg('');
    setResending(true);

    try {
      if (channel === 'email') {
        await resendOTP(recipient, purpose);
      } else {
        await sendMobileOTP(recipient);
      }
      setSuccessMsg('A new verification code has been dispatched.');
      setCooldown(60);
      setDigits(['', '', '', '', '', '']);
      inputRefs.current[0]?.focus();
    } catch (err) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        'Failed to resend code. Please wait a moment.';
      setErrorMsg(msg);
      if (err.response?.data?.retry_after) {
        setCooldown(err.response.data.retry_after);
      }
    } finally {
      setResending(false);
    }
  };

  const defaultTitle = channel === 'email' ? 'Verify Your Email' : 'Verify Mobile Number';
  const defaultSubtitle =
    channel === 'email'
      ? `We sent a 6-digit verification code to ${recipient}. Enter it below to activate your account.`
      : `We sent a 6-digit SMS code to ${recipient}.`;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: 20,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose();
      }}
    >
      <div
        className="auth-card"
        style={{
          width: '100%',
          maxWidth: 440,
          margin: 0,
          position: 'relative',
          padding: '36px 32px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          border: '1px solid var(--border-color)',
          background: 'var(--bg-card)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        {onClose && (
          <button
            onClick={onClose}
            className="navbar-icon-btn"
            style={{ position: 'absolute', top: 16, right: 16 }}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        )}

        {/* Icon Header */}
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 16,
            background: 'linear-gradient(135deg, var(--primary), var(--accent-purple))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 18px',
            boxShadow: '0 8px 20px rgba(59, 130, 246, 0.3)',
          }}
        >
          {channel === 'email' ? <Mail size={26} color="#fff" /> : <Smartphone size={26} color="#fff" />}
        </div>

        <h2 style={{ fontSize: '1.35rem', fontWeight: 800, textAlign: 'center', marginBottom: 8 }}>
          {title || defaultTitle}
        </h2>

        <p
          style={{
            fontSize: '0.85rem',
            color: 'var(--text-muted)',
            textAlign: 'center',
            lineHeight: 1.5,
            marginBottom: 24,
          }}
        >
          {subtitle || defaultSubtitle}
        </p>

        {/* Alerts */}
        {errorMsg && (
          <div className="alert-error" style={{ marginBottom: 18 }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>{errorMsg}</span>
          </div>
        )}
        {successMsg && (
          <div className="alert-success" style={{ marginBottom: 18 }}>
            <CheckCircle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>{successMsg}</span>
          </div>
        )}

        {/* 6 Digit Input Group */}
        <form onSubmit={handleSubmit}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              gap: 8,
              marginBottom: 26,
            }}
          >
            {digits.map((digit, index) => (
              <input
                key={index}
                ref={(el) => (inputRefs.current[index] = el)}
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={1}
                value={digit}
                onChange={(e) => handleChange(index, e.target.value)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                onPaste={handlePaste}
                style={{
                  width: 48,
                  height: 56,
                  fontSize: '1.4rem',
                  fontWeight: 800,
                  textAlign: 'center',
                  borderRadius: 10,
                  border: digit ? '2px solid var(--primary)' : '1px solid var(--border-color)',
                  background: 'var(--bg-input)',
                  color: 'var(--text-main)',
                  outline: 'none',
                  transition: 'all 0.15s ease',
                  fontFamily: 'monospace',
                }}
              />
            ))}
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || digits.join('').length !== 6}
            style={{
              width: '100%',
              padding: '13px',
              fontSize: '0.95rem',
              borderRadius: 10,
              gap: 8,
            }}
          >
            {submitting ? (
              <>
                <div className="spinner" />
                Verifying...
              </>
            ) : (
              <>
                Verify Code
                <ArrowRight size={17} />
              </>
            )}
          </button>
        </form>

        {/* Resend Action */}
        <div style={{ marginTop: 22, textAlign: 'center' }}>
          {cooldown > 0 ? (
            <p style={{ fontSize: '0.82rem', color: 'var(--text-dim)', margin: 0 }}>
              Resend code in <strong style={{ color: 'var(--primary)' }}>{cooldown}s</strong>
            </p>
          ) : (
            <button
              onClick={handleResend}
              disabled={resending}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--primary)',
                fontWeight: 700,
                cursor: 'pointer',
                fontSize: '0.85rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <RefreshCw size={14} className={resending ? 'spin' : ''} />
              Resend Verification Code
            </button>
          )}
        </div>

        {/* Security badge */}
        <div
          style={{
            marginTop: 24,
            textAlign: 'center',
            fontSize: '0.74rem',
            color: 'var(--text-dim)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
          }}
        >
          <ShieldCheck size={13} color="var(--accent-emerald)" />
          Single-Use Cryptographic OTP · 5-Minute Expiry
        </div>
      </div>
    </div>
  );
};

export default OTPVerificationModal;

