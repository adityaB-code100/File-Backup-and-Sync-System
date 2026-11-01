import React, { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, CheckCircle, Wifi, Activity, Clock, FileText, Folder,
} from 'lucide-react';
import api from '../services/api';

const RightSidebar = ({ refreshKey }) => {
  const [sessionStatus, setSessionStatus] = useState('idle'); // 'idle' | 'loading' | 'connected' | 'offline'
  const [lastChecked, setLastChecked] = useState(null);
  const [activities, setActivities] = useState([]);
  const [activityLoading, setActivityLoading] = useState(true);
  const [activityError, setActivityError] = useState(false);

  const formatTime = (d) => {
    if (!d) return '—';
    const now = new Date();
    const diff = Math.floor((now - new Date(d)) / 1000);
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return new Date(d).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  /**
   * Fetches recent changes (last 30 minutes) from GET /api/files/changes/?since=<ISO>.
   * Displays up to 5 most recently modified files/folders as activity.
   */
  const fetchActivity = useCallback(async () => {
    setActivityLoading(true);
    setActivityError(false);
    try {
      const since = new Date(Date.now() - 30 * 60 * 1000).toISOString();
      const res = await api.get(`/files/changes/?since=${encodeURIComponent(since)}`);
      const changes = res.data.changes || [];
      // Sort by updated_at / created_at descending, take top 5
      const sorted = [...changes].sort(
        (a, b) => new Date(b.updated_at || b.created_at) - new Date(a.updated_at || a.created_at)
      ).slice(0, 5);
      setActivities(sorted);
      setSessionStatus('connected');
      setLastChecked(new Date());
    } catch (err) {
      setActivityError(true);
      setSessionStatus('offline');
      setLastChecked(new Date());
    } finally {
      setActivityLoading(false);
    }
  }, []);

  // Refresh on mount and when refreshKey changes (file browser refreshed)
  useEffect(() => {
    setSessionStatus('loading');
    fetchActivity();
  }, [refreshKey, fetchActivity]);

  const statusColors = {
    connected: 'rgba(16,185,129,0.08)',
    offline: 'rgba(244,63,94,0.08)',
    loading: 'rgba(59,130,246,0.08)',
    idle: 'rgba(59,130,246,0.08)',
  };
  const statusBorders = {
    connected: 'rgba(16,185,129,0.2)',
    offline: 'rgba(244,63,94,0.2)',
    loading: 'rgba(59,130,246,0.2)',
    idle: 'rgba(59,130,246,0.2)',
  };
  const statusLabel = {
    connected: 'Web session connected',
    offline: 'Cannot reach server',
    loading: 'Checking...',
    idle: 'Web session',
  };
  const statusTextColor = {
    connected: 'var(--accent-emerald)',
    offline: 'var(--accent-rose)',
    loading: 'var(--primary)',
    idle: 'var(--primary)',
  };

  return (
    <div className="right-panel">
      {/* Session Status Card */}
      <div className="right-panel-card">
        <div className="right-panel-title">
          <Wifi size={15} color="var(--primary)" />
          Web Session
        </div>

        <div style={{
          display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14,
          padding: '10px 14px', borderRadius: 'var(--radius-sm)',
          background: statusColors[sessionStatus],
          border: `1px solid ${statusBorders[sessionStatus]}`,
        }}>
          {sessionStatus === 'loading' ? (
            <RefreshCw size={16} color="var(--primary)" style={{ animation: 'spin 1s linear infinite' }} />
          ) : sessionStatus === 'connected' ? (
            <CheckCircle size={16} color="var(--accent-emerald)" />
          ) : (
            <Wifi size={16} color={sessionStatus === 'offline' ? 'var(--accent-rose)' : 'var(--primary)'} />
          )}
          <div>
            <div style={{ fontSize: '0.82rem', fontWeight: 700, color: statusTextColor[sessionStatus] }}>
              {statusLabel[sessionStatus]}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 2 }}>
              <Clock size={11} style={{ display: 'inline', marginRight: 4 }} />
              {lastChecked ? `Checked: ${formatTime(lastChecked)}` : 'Not yet checked'}
            </div>
          </div>
        </div>

        <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 2 }}>
          ℹ️ Browser connection status. Desktop agent sync is shown in the desktop app.
        </div>
      </div>

      {/* Recent Activity Card — real data from /api/files/changes/ */}
      <div className="right-panel-card">
        <div className="right-panel-title">
          <Activity size={15} color="var(--accent-purple)" />
          Recent Activity
        </div>

        {activityLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[1, 2, 3].map((n) => (
              <div key={n} className="skeleton" style={{ height: 36, borderRadius: 6 }} />
            ))}
          </div>
        ) : activityError ? (
          <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', textAlign: 'center', padding: '16px 0' }}>
            Could not load recent activity.
          </div>
        ) : activities.length === 0 ? (
          <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', textAlign: 'center', padding: '16px 0' }}>
            No changes in the last 30 minutes.
          </div>
        ) : (
          <div>
            {activities.map((item, i) => (
              <div key={item.id || i} className="activity-item">
                <div className="activity-dot" style={{
                  background: item.type === 'folder' ? 'var(--accent-cyan)' : 'var(--primary)',
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: '0.8rem', lineHeight: 1.4,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {item.type === 'folder'
                      ? <><Folder size={11} style={{ display: 'inline', marginRight: 3 }} />{item.name}</>
                      : <><FileText size={11} style={{ display: 'inline', marginRight: 3 }} />{item.name}</>}
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 2 }}>
                    Modified {formatTime(item.updated_at || item.created_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default RightSidebar;
