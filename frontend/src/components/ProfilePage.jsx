import React, { useState, useEffect } from 'react';
import {
  User, Mail, Phone, Calendar, MapPin, Globe, Lock, ShieldCheck,
  CheckCircle, AlertCircle, RefreshCw, KeyRound, Save, Smartphone,
  Edit3, X, Eye, Check
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import OTPVerificationModal from './OTPVerificationModal';
import {
  SUPPORTED_COUNTRIES,
  DIAL_COUNTRIES,
  LOCATION_DATA
} from '../data/locations.js';
import {
  parseStoredMobile,
  validateNationalNumber,
  getNormalizedE164,
  formatDisplayMobile
} from '../utils/phoneUtils.js';

const validateDob = (val) => {
  if (!val) return ''; // optional
  const d = new Date(val);
  if (isNaN(d.getTime())) return 'Enter a valid date.';
  if (d >= new Date()) return 'Date of birth cannot be today or a future date.';
  return '';
};

const validateProfileName = (val) => {
  const trimmed = val.trim();
  if (!trimmed) return ''; // optional
  if (trimmed.length < 2) return 'Name must be at least 2 characters.';
  if (trimmed.length > 100) return 'Name must not exceed 100 characters.';
  if (!/^[a-zA-Z\s'\-\u00C0-\u024F]+$/.test(trimmed)) return 'Name contains invalid characters.';
  return '';
};

const ProfilePage = () => {
  const { user, updateProfile, sendMobileOTP, changePassword, refreshUser } = useAuth();

  // Mode state: Default is View Mode (false)
  const [isEditing, setIsEditing] = useState(false);

  // Profile Form State
  const [fullName, setFullName] = useState('');
  const [mobileCountryCode, setMobileCountryCode] = useState('IN');
  const [nationalNumber, setNationalNumber] = useState('');
  const [dob, setDob] = useState('');
  const [gender, setGender] = useState('');
  const [country, setCountry] = useState('');
  const [state, setState] = useState('');
  const [city, setCity] = useState('');
  const [address, setAddress] = useState('');

  // Password Change Form State
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [pwSubmitting, setPwSubmitting] = useState(false);
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwError, setPwError] = useState('');

  // Profile Save State
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState('');
  const [saveError, setSaveError] = useState('');

  // Field-level errors
  const [nameErr, setNameErr] = useState('');
  const [mobileErr, setMobileErr] = useState('');
  const [dobErr, setDobErr] = useState('');
  const [locationErr, setLocationErr] = useState('');

  // SMS OTP Modal State
  const [showSMSModal, setShowSMSModal] = useState(false);
  const [sendingSMS, setSendingSMS] = useState(false);
  const [activeSMSPhone, setActiveSMSPhone] = useState('');

  // Sync state with user data
  const syncStateWithUser = () => {
    if (user) {
      setFullName(user.full_name || '');
      const parsedMobile = parseStoredMobile(user.mobile_number || '');
      setMobileCountryCode(parsedMobile.countryCode || 'IN');
      setNationalNumber(parsedMobile.nationalNumber || '');
      setDob(user.dob || '');
      setGender(user.gender || '');
      setCountry(user.country || '');
      setState(user.state || '');
      setCity(user.city || '');
      setAddress(user.address || '');
    }
  };

  useEffect(() => {
    syncStateWithUser();
  }, [user]);

  // Mode Handlers
  const handleEnterEditMode = () => {
    syncStateWithUser();
    setNameErr('');
    setMobileErr('');
    setDobErr('');
    setLocationErr('');
    setSaveError('');
    setSaveSuccess('');
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    syncStateWithUser();
    setNameErr('');
    setMobileErr('');
    setDobErr('');
    setLocationErr('');
    setSaveError('');
    setIsEditing(false);
  };

  // Cascading Location Handlers
  const handleCountryChange = (e) => {
    const newCountry = e.target.value;
    setCountry(newCountry);
    // When country changes, reset state and city
    setState('');
    setCity('');
    if (locationErr) setLocationErr('');
  };

  const handleStateChange = (e) => {
    const newState = e.target.value;
    setState(newState);
    // When state changes, reset city
    setCity('');
    if (locationErr) setLocationErr('');
  };

  const handleCityChange = (e) => {
    setCity(e.target.value);
    if (locationErr) setLocationErr('');
  };

  // Mobile Input Handlers
  const handleCountryCodeChange = (e) => {
    const newCode = e.target.value;
    setMobileCountryCode(newCode);
    if (nationalNumber) {
      setMobileErr(validateNationalNumber(nationalNumber, newCode));
    }
  };

  const handleNationalNumberChange = (e) => {
    let val = e.target.value;
    // Disallow typing or pasting +91, +44, +1 or '+'
    val = val.replace(/^\+91|^\+44|^\+1|^\+/, '');
    // Numbers only
    val = val.replace(/[^\d]/g, '');
    setNationalNumber(val);
    if (mobileErr) setMobileErr('');
  };

  // Save Profile Handler
  const handleProfileSave = async (e) => {
    if (e) e.preventDefault();
    setSaveSuccess('');
    setSaveError('');

    // Client-side validation
    const nErr = validateProfileName(fullName);
    const mErr = validateNationalNumber(nationalNumber, mobileCountryCode);
    const dErr = validateDob(dob);

    let lErr = '';
    if (state && !country) {
      lErr = 'Please select a country first.';
    } else if (city && !state) {
      lErr = 'Please select a state / province first.';
    }

    setNameErr(nErr);
    setMobileErr(mErr);
    setDobErr(dErr);
    setLocationErr(lErr);

    if (nErr || mErr || dErr || lErr) return;

    setSaving(true);

    try {
      // Calculate normalized E.164 phone number
      const normalizedMobile = nationalNumber.trim()
        ? getNormalizedE164(nationalNumber, mobileCountryCode)
        : '';

      const res = await updateProfile({
        full_name: fullName.trim(),
        mobile_number: normalizedMobile,
        dob,
        gender,
        country: country.trim(),
        state: state.trim(),
        city: city.trim(),
        address: address.trim(),
      });

      setSaveSuccess(res.message || 'Profile updated successfully!');
      setIsEditing(false); // Return to View Mode
      setTimeout(() => setSaveSuccess(''), 4000);
    } catch (err) {
      setSaveError(err.response?.data?.error || 'Failed to update profile. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // SMS Verification Flow
  const handleStartMobileVerification = async () => {
    setSaveError('');
    setMobileErr('');

    let targetPhone = '';

    if (isEditing) {
      if (!nationalNumber.trim()) {
        setMobileErr('Please enter a mobile number first.');
        return;
      }
      const mErr = validateNationalNumber(nationalNumber, mobileCountryCode);
      if (mErr) {
        setMobileErr(mErr);
        return;
      }
      targetPhone = getNormalizedE164(nationalNumber, mobileCountryCode);
    } else {
      if (!user?.mobile_number) {
        setSaveError('Please add a mobile number in Edit Profile first.');
        return;
      }
      targetPhone = user.mobile_number;
    }

    setSendingSMS(true);
    try {
      await sendMobileOTP(targetPhone);
      setActiveSMSPhone(targetPhone);
      setShowSMSModal(true);
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to send SMS verification code.';
      setSaveError(msg);
      if (isEditing) setMobileErr(msg);
    } finally {
      setSendingSMS(false);
    }
  };

  // Password Change Handler
  const handlePasswordChange = async (e) => {
    e.preventDefault();
    setPwSuccess('');
    setPwError('');

    if (!currentPw) {
      setPwError('Please enter your current password.');
      return;
    }
    if (!newPw) {
      setPwError('Please enter your new password.');
      return;
    }
    if (newPw.length < 8) {
      setPwError('New password must be at least 8 characters.');
      return;
    }
    if (newPw !== confirmPw) {
      setPwError('Passwords do not match.');
      return;
    }

    setPwSubmitting(true);
    try {
      await changePassword(currentPw, newPw);
      setPwSuccess('Password changed successfully.');
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
      setTimeout(() => setPwSuccess(''), 4000);
    } catch (err) {
      setPwError(err.response?.data?.error || 'Failed to change password. Check your current password.');
    } finally {
      setPwSubmitting(false);
    }
  };

  const userInitial = (user?.full_name || user?.email || 'U')[0].toUpperCase();

  return (
    <div className="profile-container" style={{ maxWidth: 880, margin: '0 auto', paddingBottom: 60 }}>
      {/* Profile Header Card */}
      <div
        className="auth-card"
        style={{
          maxWidth: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 24,
          padding: 28,
          marginBottom: 24,
          background: 'var(--bg-card)',
          borderRadius: 16,
          border: '1px solid var(--border-color)',
        }}
      >
        <div
          style={{
            width: 76,
            height: 76,
            borderRadius: '50%',
            background: 'linear-gradient(135deg, var(--primary), var(--accent-purple))',
            color: '#fff',
            fontSize: '2rem',
            fontWeight: 800,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: '0 8px 24px rgba(59, 130, 246, 0.35)',
          }}
        >
          {userInitial}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <h2 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em' }}>
              {user?.full_name || 'VaultCloud Member'}
            </h2>
            {user?.is_email_verified && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 9px',
                  borderRadius: 99,
                  background: 'rgba(16, 185, 129, 0.12)',
                  color: 'var(--accent-emerald)',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                }}
              >
                <CheckCircle size={12} /> Email Verified
              </span>
            )}
            {user?.is_mobile_verified ? (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 9px',
                  borderRadius: 99,
                  background: 'rgba(16, 185, 129, 0.12)',
                  color: 'var(--accent-emerald)',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                }}
              >
                <CheckCircle size={12} /> Mobile Verified
              </span>
            ) : (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 9px',
                  borderRadius: 99,
                  background: 'rgba(245, 158, 11, 0.12)',
                  color: 'var(--accent-amber, #f59e0b)',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                }}
              >
                <AlertCircle size={12} /> Mobile Unverified
              </span>
            )}
          </div>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', margin: '4px 0 0 0' }}>
            {user?.email}
          </p>
        </div>
      </div>

      {/* Personal Information Card */}
      <div
        className="auth-card"
        style={{
          maxWidth: '100%',
          padding: 32,
          marginBottom: 24,
          background: 'var(--bg-card)',
          borderRadius: 16,
          border: '1px solid var(--border-color)',
        }}
      >
        {/* Card Header with View/Edit mode indicator & Action buttons */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <User size={20} color="var(--primary)" />
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0 }}>Personal Information</h3>
            {isEditing ? (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 8px',
                  borderRadius: 99,
                  background: 'rgba(59, 130, 246, 0.15)',
                  color: 'var(--primary)',
                  fontSize: '0.74rem',
                  fontWeight: 700,
                }}
              >
                <Edit3 size={11} /> Edit Mode
              </span>
            ) : (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 8px',
                  borderRadius: 99,
                  background: 'rgba(255, 255, 255, 0.06)',
                  color: 'var(--text-muted)',
                  fontSize: '0.74rem',
                  fontWeight: 600,
                }}
              >
                <Eye size={11} /> View Mode
              </span>
            )}
          </div>

          <div>
            {!isEditing ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleEnterEditMode}
                style={{ padding: '8px 18px', gap: 6, fontSize: '0.86rem', borderRadius: 8 }}
              >
                <Edit3 size={15} /> Edit Profile
              </button>
            ) : (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={handleCancelEdit}
                  disabled={saving}
                  style={{ padding: '8px 14px', gap: 6, fontSize: '0.86rem' }}
                >
                  <X size={15} /> Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleProfileSave}
                  disabled={saving}
                  style={{ padding: '8px 18px', gap: 6, fontSize: '0.86rem', borderRadius: 8 }}
                >
                  {saving ? (
                    <>
                      <div className="spinner" /> Saving...
                    </>
                  ) : (
                    <>
                      <Save size={15} /> Save Changes
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {saveSuccess && (
          <div className="alert-success" style={{ marginBottom: 18 }}>
            <CheckCircle size={16} /> {saveSuccess}
          </div>
        )}
        {saveError && (
          <div className="alert-error" style={{ marginBottom: 18 }}>
            <AlertCircle size={16} /> {saveError}
          </div>
        )}

        {/* ── VIEW MODE (Read-only presentation) ── */}
        {!isEditing ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
            {/* Full Name */}
            <div className="profile-view-card">
              <span className="profile-view-label"><User size={13} /> Full Name</span>
              <span className="profile-view-value">
                {user?.full_name || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>

            {/* Email Address (Primary) */}
            <div className="profile-view-card">
              <span className="profile-view-label"><Mail size={13} /> Email Address (Primary)</span>
              <span className="profile-view-value" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <span>{user?.email || '—'}</span>
                {user?.is_email_verified && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--accent-emerald)', display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                    <CheckCircle size={11} /> Verified
                  </span>
                )}
              </span>
            </div>

            {/* Mobile Number */}
            <div className="profile-view-card" style={{ gridColumn: '1 / -1' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                <div>
                  <span className="profile-view-label"><Smartphone size={13} /> Mobile Number (Twilio SMS OTP)</span>
                  <span className="profile-view-value" style={{ display: 'block', marginTop: 4 }}>
                    {formatDisplayMobile(user?.mobile_number) || (
                      <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>
                        No mobile number added. Click Edit Profile to add one.
                      </span>
                    )}
                  </span>
                </div>

                {user?.mobile_number && (
                  <div>
                    {user?.is_mobile_verified ? (
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '4px 10px',
                          borderRadius: 99,
                          background: 'rgba(16, 185, 129, 0.12)',
                          color: 'var(--accent-emerald)',
                          fontSize: '0.76rem',
                          fontWeight: 700,
                        }}
                      >
                        <CheckCircle size={12} /> Mobile Verified
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={handleStartMobileVerification}
                        disabled={sendingSMS}
                        style={{ padding: '7px 14px', fontSize: '0.82rem', gap: 6 }}
                      >
                        {sendingSMS ? (
                          <>
                            <div className="spinner" /> Sending...
                          </>
                        ) : (
                          <>
                            <Phone size={14} /> Verify via SMS
                          </>
                        )}
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Date of Birth */}
            <div className="profile-view-card">
              <span className="profile-view-label"><Calendar size={13} /> Date of Birth</span>
              <span className="profile-view-value">
                {user?.dob || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>

            {/* Gender */}
            <div className="profile-view-card">
              <span className="profile-view-label"><User size={13} /> Gender</span>
              <span className="profile-view-value">
                {user?.gender || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>

            {/* Country */}
            <div className="profile-view-card">
              <span className="profile-view-label"><Globe size={13} /> Country</span>
              <span className="profile-view-value">
                {user?.country || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>

            {/* State / Province */}
            <div className="profile-view-card">
              <span className="profile-view-label"><MapPin size={13} /> State / Province</span>
              <span className="profile-view-value">
                {user?.state || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>

            {/* City / Town / Village */}
            <div className="profile-view-card">
              <span className="profile-view-label"><MapPin size={13} /> City / Town / Village</span>
              <span className="profile-view-value">
                {user?.city || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>

            {/* Address */}
            <div className="profile-view-card" style={{ gridColumn: '1 / -1' }}>
              <span className="profile-view-label"><MapPin size={13} /> Residential / Postal Address</span>
              <span className="profile-view-value">
                {user?.address || <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}>Not provided</span>}
              </span>
            </div>
          </div>
        ) : (
          /* ── EDIT MODE (Active Input Controls) ── */
          <form onSubmit={handleProfileSave}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
              {/* Full Name */}
              <div className="form-group">
                <label className="form-label">Full Name <span style={{ fontWeight: 400, color: 'var(--text-dim)', fontSize: '0.8rem' }}>(optional)</span></label>
                <div className="input-wrapper">
                  <User size={17} className="input-icon-left" />
                  <input
                    type="text"
                    className={`input-field has-icon-left${nameErr ? ' input-error' : ''}`}
                    placeholder="John Doe"
                    value={fullName}
                    onChange={(e) => { setFullName(e.target.value); if (nameErr) setNameErr(''); }}
                    onBlur={() => setNameErr(validateProfileName(fullName))}
                    maxLength={100}
                  />
                </div>
                {nameErr && <span className="form-error">{nameErr}</span>}
              </div>

              {/* Email Address (Read-only) */}
              <div className="form-group">
                <label className="form-label">Email Address (Primary)</label>
                <div className="input-wrapper">
                  <Mail size={17} className="input-icon-left" />
                  <input
                    type="email"
                    className="input-field has-icon-left"
                    value={user?.email || ''}
                    disabled
                    style={{ opacity: 0.7, cursor: 'not-allowed' }}
                  />
                </div>
                <span style={{ fontSize: '0.74rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
                  Account email address cannot be changed directly.
                </span>
              </div>

              {/* Mobile Number: Separate Country Dialing Code Dropdown + Mobile Input */}
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">
                  Mobile Number (Twilio SMS OTP) <span style={{ fontWeight: 400, color: 'var(--text-dim)', fontSize: '0.8rem' }}>(optional)</span>
                </label>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  {/* Country Dialing Code Dropdown */}
                  <div style={{ minWidth: 185, flexShrink: 0 }}>
                    <select
                      className="input-field"
                      value={mobileCountryCode}
                      onChange={handleCountryCodeChange}
                      aria-label="Country Dialing Code"
                      style={{ paddingLeft: 12, fontWeight: 500 }}
                    >
                      {DIAL_COUNTRIES.map((c) => (
                        <option key={c.code} value={c.code}>
                          {c.flag} {c.name} ({c.dialCode})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Mobile Number Input */}
                  <div className="input-wrapper" style={{ flex: '1 1 220px' }}>
                    <Smartphone size={17} className="input-icon-left" />
                    <input
                      type="tel"
                      inputMode="numeric"
                      className={`input-field has-icon-left${mobileErr ? ' input-error' : ''}`}
                      placeholder={
                        mobileCountryCode === 'IN'
                          ? '9876543210 (10 digits)'
                          : mobileCountryCode === 'GB'
                          ? '7911123456 (UK mobile)'
                          : '4155552671 (10 digits)'
                      }
                      value={nationalNumber}
                      onChange={handleNationalNumberChange}
                      onBlur={() => setMobileErr(validateNationalNumber(nationalNumber, mobileCountryCode))}
                      maxLength={15}
                    />
                  </div>

                  {/* Verify via SMS Button */}
                  {nationalNumber.trim() && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleStartMobileVerification}
                      disabled={sendingSMS || !nationalNumber.trim()}
                      style={{ whiteSpace: 'nowrap', padding: '10px 16px', fontSize: '0.85rem' }}
                    >
                      {sendingSMS ? (
                        <>
                          <div className="spinner" /> Sending...
                        </>
                      ) : (
                        <>
                          <Phone size={15} /> Verify via SMS
                        </>
                      )}
                    </button>
                  )}
                </div>

                <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
                  Select dialing code and enter mobile number without country prefix or symbols.
                </span>
                {mobileErr && <span className="form-error">{mobileErr}</span>}
              </div>

              {/* Date of Birth */}
              <div className="form-group">
                <label className="form-label">Date of Birth</label>
                <div className="input-wrapper">
                  <Calendar size={17} className="input-icon-left" />
                  <input
                    type="date"
                    className={`input-field has-icon-left${dobErr ? ' input-error' : ''}`}
                    value={dob}
                    onChange={(e) => { setDob(e.target.value); if (dobErr) setDobErr(''); }}
                    onBlur={() => setDobErr(validateDob(dob))}
                    max={new Date(new Date().setDate(new Date().getDate() - 1)).toISOString().split('T')[0]}
                  />
                </div>
                {dobErr && <span className="form-error">{dobErr}</span>}
              </div>

              {/* Gender */}
              <div className="form-group">
                <label className="form-label">Gender</label>
                <select
                  className="input-field"
                  value={gender}
                  onChange={(e) => setGender(e.target.value)}
                  style={{ paddingLeft: 12 }}
                >
                  <option value="">Select Gender</option>
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Non-Binary">Non-Binary</option>
                  <option value="Prefer not to say">Prefer not to say</option>
                </select>
              </div>

              {/* Cascading Location: Country */}
              <div className="form-group">
                <label className="form-label">Country</label>
                <div className="input-wrapper">
                  <Globe size={17} className="input-icon-left" />
                  <select
                    className="input-field has-icon-left"
                    value={country}
                    onChange={handleCountryChange}
                  >
                    <option value="">Select Country</option>
                    {SUPPORTED_COUNTRIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Cascading Location: State / Province */}
              <div className="form-group">
                <label className="form-label">State / Province</label>
                <div className="input-wrapper">
                  <MapPin size={17} className="input-icon-left" />
                  <select
                    className="input-field has-icon-left"
                    value={state}
                    onChange={handleStateChange}
                    disabled={!country}
                    style={{ opacity: !country ? 0.6 : 1, cursor: !country ? 'not-allowed' : 'pointer' }}
                  >
                    <option value="">
                      {!country ? 'First select a country...' : 'Select State / Province'}
                    </option>
                    {country && LOCATION_DATA[country] && Object.keys(LOCATION_DATA[country]).map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Cascading Location: City / Town / Village */}
              <div className="form-group">
                <label className="form-label">City / Town / Village</label>
                <div className="input-wrapper">
                  <MapPin size={17} className="input-icon-left" />
                  <select
                    className="input-field has-icon-left"
                    value={city}
                    onChange={handleCityChange}
                    disabled={!state}
                    style={{ opacity: !state ? 0.6 : 1, cursor: !state ? 'not-allowed' : 'pointer' }}
                  >
                    <option value="">
                      {!state ? 'First select a state...' : 'Select City / Town / Village'}
                    </option>
                    {country && state && LOCATION_DATA[country]?.[state]?.map((cty) => (
                      <option key={cty} value={cty}>{cty}</option>
                    ))}
                  </select>
                </div>
                {state && (
                  <span style={{ fontSize: '0.74rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
                    Supported location list for {state}
                  </span>
                )}
                {locationErr && <span className="form-error">{locationErr}</span>}
              </div>

              {/* Street Address */}
              <div className="form-group" style={{ gridColumn: '1 / -1' }}>
                <label className="form-label">Residential / Postal Address</label>
                <div className="input-wrapper">
                  <MapPin size={17} className="input-icon-left" />
                  <input
                    type="text"
                    className="input-field has-icon-left"
                    placeholder="123 Market Street, Suite 400"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                    maxLength={255}
                  />
                </div>
              </div>
            </div>

            {/* Bottom Edit Actions */}
            <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleCancelEdit}
                disabled={saving}
                style={{ padding: '10px 20px', fontSize: '0.9rem' }}
              >
                <X size={16} /> Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={saving}
                style={{ padding: '10px 22px', fontSize: '0.9rem', borderRadius: 8 }}
              >
                {saving ? (
                  <>
                    <div className="spinner" /> Saving Changes...
                  </>
                ) : (
                  <>
                    <Save size={16} /> Save Changes
                  </>
                )}
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Security & Password Change Card */}
      <div
        className="auth-card"
        style={{
          maxWidth: '100%',
          padding: 32,
          background: 'var(--bg-card)',
          borderRadius: 16,
          border: '1px solid var(--border-color)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <KeyRound size={20} color="var(--primary)" />
          <h3 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0 }}>Change Password</h3>
        </div>

        {pwSuccess && (
          <div className="alert-success" style={{ marginBottom: 18 }}>
            <CheckCircle size={16} /> {pwSuccess}
          </div>
        )}
        {pwError && (
          <div className="alert-error" style={{ marginBottom: 18 }}>
            <AlertCircle size={16} /> {pwError}
          </div>
        )}

        <form onSubmit={handlePasswordChange}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
            <div className="form-group">
              <label className="form-label">Current Password</label>
              <div className="input-wrapper">
                <Lock size={17} className="input-icon-left" />
                <input
                  type="password"
                  className="input-field has-icon-left"
                  placeholder="••••••••••"
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">New Password</label>
              <div className="input-wrapper">
                <Lock size={17} className="input-icon-left" />
                <input
                  type="password"
                  className="input-field has-icon-left"
                  placeholder="At least 8 characters"
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Confirm New Password</label>
              <div className="input-wrapper">
                <Lock size={17} className="input-icon-left" />
                <input
                  type="password"
                  className="input-field has-icon-left"
                  placeholder="Repeat new password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                />
              </div>
            </div>
          </div>

          <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={pwSubmitting}
              style={{ padding: '10px 22px', fontSize: '0.9rem' }}
            >
              {pwSubmitting ? (
                <>
                  <div className="spinner" /> Updating...
                </>
              ) : (
                <>
                  <Lock size={16} /> Update Password
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* SMS Verification Modal */}
      <OTPVerificationModal
        isOpen={showSMSModal}
        onClose={() => setShowSMSModal(false)}
        recipient={activeSMSPhone || user?.mobile_number}
        channel="sms"
        purpose="mobile_verification"
        onSuccess={() => {
          setSaveSuccess('Mobile number verified successfully via Twilio Verify!');
          refreshUser();
        }}
      />
    </div>
  );
};

export default ProfilePage;
