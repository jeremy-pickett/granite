'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';

interface InjectionReport {
  report_id: number;
  image_name: string;
  image_hash: string;
  width: number;
  height: number;
  profile: string;
  layers_active: string[];
  total_markers: number;
  total_sentinels: number;
  heatmap_path: string;
  histogram_path: string;
  report_json_path: string;
  created_at: string;
}

interface ProfileData {
  user: {
    email: string;
    display_name: string;
    display_name_custom: string | null;
    photo_url: string | null;
    role: string;
    subscription_tier: string;
    created_at: string;
    last_login: string;
  };
  stats: {
    watchlist_count: number;
    alert_count: number;
    report_count: number;
  };
  linked_securities: { ticker: string; name: string; security_type: string }[];
  recent_activity: { action: string; resource_type: string; resource_id: string | null; event_time: string }[];
  injection_reports: InjectionReport[];
}

interface LockerFile {
  file_id: number;
  upload_group: string;
  file_type: string;
  file_name: string;
  mime_type: string;
  file_size: number;
  image_hash: string | null;
  profile: string | null;
  created_at: string;
}

interface LockerGroup {
  upload_group: string;
  image_hash: string | null;
  profile: string | null;
  created_at: string;
  files: LockerFile[];
}

const permissionsByRole: Record<string, string[]> = {
  admin: ['Full access', 'Manage users', 'API keys', 'All securities', 'Export data', 'Configure alerts'],
  analyst: ['View all securities', 'Watchlist', 'Alerts', 'Export data', 'Research reports'],
  user: ['View securities', 'Watchlist (up to 20)', 'Alerts (up to 10)', 'Research reports'],
  free: ['View securities', 'Watchlist (up to 5)', 'Alerts (up to 3)'],
};

const tierColors: Record<string, string> = {
  admin: 'text-ald-red', pro: 'text-ald-amber', analyst: 'text-ald-cyan',
  free: 'text-ald-text-dim', user: 'text-ald-blue',
};

const FILE_TYPE_LABELS: Record<string, string> = {
  injected: 'JPEG+DQT', injected_png: 'PNG', heatmap: 'Heatmap',
  manifest: 'Manifest', histogram: 'Histogram', verify_report: 'Verify',
  pdf: 'PDF', original: 'Original',
};

function LogoImg({ ticker }: { ticker: string }) {
  const [err, setErr] = useState(false);
  if (err) {
    return (
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-ald-surface-2 font-mono text-xs text-ald-text-dim">
        {ticker.slice(0, 2)}
      </div>
    );
  }
  return (
    <Image src={`/logos/${ticker}.png`} alt={ticker} width={24} height={24}
      className="h-6 w-6 shrink-0 rounded" onError={() => setErr(true)} />
  );
}

export default function ProfilePage() {
  const { user, isAuthenticated, isLoading, signOut, getIdToken } = useAuth();
  const router = useRouter();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [groups, setGroups] = useState<LockerGroup[]>([]);
  const [totalFiles, setTotalFiles] = useState(0);
  const [lockerLoading, setLockerLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = useCallback(async () => {
    setLoadingProfile(true);
    try {
      const token = await getIdToken();
      if (!token) { setLoadingProfile(false); return; }
      const res = await fetch('/api/profile', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setProfile(await res.json());
    } catch {}
    setLoadingProfile(false);
  }, [getIdToken]);

  const fetchLocker = useCallback(async () => {
    try {
      const token = await getIdToken();
      if (!token) { setLockerLoading(false); return; }
      const res = await fetch('/api/locker', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setGroups(data.groups);
        setTotalFiles(data.total_files);
      }
    } catch {}
    setLockerLoading(false);
  }, [getIdToken]);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/alidade/login');
    } else if (isAuthenticated) {
      fetchProfile();
      fetchLocker();
    }
  }, [isAuthenticated, isLoading, router, fetchProfile, fetchLocker]);

  const handleSignOut = async () => { await signOut(); router.push('/alidade'); };

  async function downloadFile(fileId: number, fileName: string) {
    try {
      const token = await getIdToken();
      const res = await fetch(`/api/locker/download?file_id=${fileId}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = fileName; a.click(); URL.revokeObjectURL(url);
    } catch { setError('Download failed'); }
  }

  async function deleteGroup(uploadGroup: string) {
    try {
      const token = await getIdToken();
      const res = await fetch('/api/locker', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ upload_group: uploadGroup }),
      });
      if (res.ok) {
        setGroups(prev => prev.filter(g => g.upload_group !== uploadGroup));
        setTotalFiles(prev => prev - (groups.find(g => g.upload_group === uploadGroup)?.files.length ?? 0));
      }
    } catch { setError('Delete failed'); }
  }

  if (isLoading || loadingProfile) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  if (!isAuthenticated) return null;

  const role = profile?.user.role ?? 'user';
  const tier = profile?.user.subscription_tier ?? 'free';
  const permissions = permissionsByRole[role] ?? permissionsByRole['user'];

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="mb-8 text-2xl font-light tracking-tight text-ald-ivory">Profile</h1>

      {error && (
        <div className="mb-4 rounded border border-ald-red/30 bg-ald-red/5 p-3 font-mono text-sm text-ald-red">{error}</div>
      )}

      {/* Display Name */}
      <div className="mb-6 rounded-lg border border-ald-blue/20 bg-ald-surface p-6">
        <h3 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-text-dim">Display Name</h3>
        <p className="mb-4 text-sm text-ald-text-muted">
          This is the name shown on your comments. Change it anytime.
        </p>
        <DisplayNameRow
          initialName={profile?.user.display_name_custom || profile?.user.display_name || user?.displayName || ''}
          getIdToken={getIdToken}
        />
      </div>

      {/* User Info */}
      <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-6">
        <div className="flex items-center gap-4 mb-6">
          {user?.photoURL ? (
            <img src={user.photoURL} alt="" className="h-14 w-14 rounded-full border border-ald-border" />
          ) : (
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-ald-blue/20 text-ald-blue font-mono text-lg">
              {user?.displayName?.[0] || '?'}
            </div>
          )}
          <div>
            <h2 className="text-lg text-ald-ivory">{profile?.user.display_name_custom || profile?.user.display_name || user?.displayName || 'User'}</h2>
            <p className="font-mono text-sm text-ald-text-dim">{profile?.user.email || user?.email}</p>
          </div>
        </div>
        {profile && (
          <div className="space-y-3">
            <Row label="Role" value={role} className={tierColors[role]} />
            <Row label="Subscription" value={tier} className={tierColors[tier]} />
            <Row label="Member Since" value={new Date(profile.user.created_at).toLocaleDateString()} />
            <Row label="Last Login" value={new Date(profile.user.last_login).toLocaleString()} />
          </div>
        )}
      </div>

      {/* Permissions + Stats */}
      {profile && (
        <>
          <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-6">
            <h3 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-text-dim">Permissions</h3>
            <div className="flex flex-wrap gap-2">
              {permissions.map((perm) => (
                <span key={perm} className="rounded bg-ald-blue/10 border border-ald-blue/20 px-3 py-1 font-mono text-sm text-ald-blue">{perm}</span>
              ))}
            </div>
          </div>

          <div className="mb-6 grid grid-cols-3 gap-3">
            <StatCard value={profile.stats.watchlist_count} label="Watchlist" />
            <StatCard value={profile.stats.alert_count} label="Alerts" />
            <StatCard value={profile.stats.report_count ?? 0} label="Reports" />
          </div>
        </>
      )}

      {/* ── Locker ── */}
      <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-mono text-sm uppercase tracking-wider text-ald-text-dim">
            Locker {!lockerLoading && <span className="normal-case text-ald-text-dim">— {totalFiles} file{totalFiles !== 1 ? 's' : ''}</span>}
          </h3>
          <Link href="/inject"
            className="rounded border border-ald-blue/30 px-3 py-1 font-mono text-xs uppercase tracking-wider text-ald-blue hover:bg-ald-blue hover:text-ald-void transition-colors">
            Upload
          </Link>
        </div>

        {lockerLoading ? (
          <div className="flex justify-center py-8">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
          </div>
        ) : groups.length === 0 ? (
          <p className="py-6 text-center font-mono text-sm text-ald-text-dim">No files yet. Upload via Granite to get started.</p>
        ) : (
          <div className="space-y-3">
            {groups.map((group) => {
              const isVerify = group.files.some(f => f.file_type === 'verify_report');
              return (
                <div key={group.upload_group} className="rounded border border-ald-border bg-ald-deep">
                  <div className="flex items-center justify-between px-4 py-2 border-b border-ald-border/50">
                    <div className="flex items-center gap-3">
                      <span className={`rounded px-1.5 py-0.5 font-mono text-xs uppercase ${
                        isVerify ? 'bg-ald-cyan/10 text-ald-cyan' : 'bg-ald-blue/10 text-ald-blue'
                      }`}>
                        {isVerify ? 'verify' : 'inject'}
                      </span>
                      {group.image_hash && <span className="font-mono text-xs text-ald-text-dim">{group.image_hash}</span>}
                      <span className="font-mono text-xs text-ald-text-dim">
                        {new Date(group.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <button
                      onClick={() => deleteGroup(group.upload_group)}
                      className="rounded px-2 py-0.5 font-mono text-xs text-ald-text-dim hover:text-ald-red transition-colors"
                      title="Delete upload group and files"
                    >
                      Delete
                    </button>
                  </div>
                  <div className="divide-y divide-ald-border/30">
                    {group.files.map((f) => (
                      <button key={f.file_id} onClick={() => downloadFile(f.file_id, f.file_name)}
                        className="flex w-full items-center justify-between px-4 py-2 text-left text-sm transition-colors hover:bg-ald-surface-2">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-ald-text">{f.file_name}</span>
                          <span className="font-mono text-xs text-ald-text-dim">{FILE_TYPE_LABELS[f.file_type] || f.file_type}</span>
                        </div>
                        <span className="font-mono text-xs text-ald-text-dim">{formatBytes(f.file_size)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Linked Securities */}
      {profile && profile.linked_securities.length > 0 && (
        <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-6">
          <h3 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-text-dim">Linked Securities</h3>
          <div className="space-y-2">
            {profile.linked_securities.map((sec) => (
              <Link key={sec.ticker} href={`/alidade/research/${sec.ticker}`}
                className="flex items-center gap-3 rounded p-2 hover:bg-ald-surface-2 transition-colors">
                <LogoImg ticker={sec.ticker} />
                <span className="font-mono text-sm text-ald-ivory">{sec.ticker}</span>
                <span className="text-sm text-ald-text-dim">{sec.name}</span>
                <span className="ml-auto rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-sm uppercase text-ald-text-dim">{sec.security_type}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Recent Activity */}
      {profile && profile.recent_activity.length > 0 && (
        <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-6">
          <h3 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-text-dim">Recent Activity</h3>
          <div className="space-y-2">
            {profile.recent_activity.map((activity, i) => (
              <div key={i} className="flex items-center justify-between py-1 border-b border-ald-border/30 last:border-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-ald-text">{activity.action}</span>
                  {activity.resource_id && <span className="font-mono text-sm text-ald-text-dim">{activity.resource_id}</span>}
                </div>
                <span className="font-mono text-sm text-ald-text-dim">{new Date(activity.event_time).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sign Out */}
      <div className="rounded-lg border border-ald-red/20 bg-ald-red/5 p-6">
        <h3 className="mb-2 font-mono text-sm uppercase tracking-wider text-ald-red">Danger Zone</h3>
        <p className="mb-4 text-sm text-ald-text-dim">Sign out of your account. You can sign back in at any time.</p>
        <button onClick={handleSignOut}
          className="rounded border border-ald-red/30 px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-red hover:bg-ald-red hover:text-white transition-colors cursor-pointer">
          Sign Out
        </button>
      </div>
    </div>
  );
}

function DisplayNameRow({ initialName, getIdToken }: { initialName: string; getIdToken: () => Promise<string | null> }) {
  const [name, setName] = useState(initialName);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Sync when profile data arrives after initial render
  useEffect(() => {
    if (initialName) setName(initialName);
  }, [initialName]);

  async function handleSave() {
    setSaving(true);
    try {
      const token = await getIdToken();
      const res = await fetch('/api/profile', {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name_custom: name }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch {}
    setSaving(false);
  }

  return (
    <div className="flex items-center justify-between border-b border-ald-border/50 pb-2">
      <span className="font-mono text-sm text-ald-text-dim">Display Name</span>
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Choose a name..."
          className="w-48 rounded border border-ald-border bg-ald-deep px-2 py-1 font-mono text-sm text-ald-text focus:border-ald-blue/50 focus:outline-none"
        />
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded bg-ald-blue/10 border border-ald-blue/30 px-3 py-1 font-mono text-xs text-ald-blue hover:bg-ald-blue hover:text-white disabled:opacity-40 transition-colors"
        >
          {saved ? 'Saved!' : saving ? '...' : 'Save'}
        </button>
      </div>
    </div>
  );
}

function Row({ label, value, className = 'text-ald-text' }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex justify-between border-b border-ald-border/50 pb-2">
      <span className="font-mono text-sm text-ald-text-dim">{label}</span>
      <span className={`font-mono text-sm uppercase ${className}`}>{value}</span>
    </div>
  );
}

function StatCard({ value, label }: { value: number; label: string }) {
  return (
    <div className="rounded-lg border border-ald-border bg-ald-surface p-4 text-center">
      <span className="block font-mono text-2xl font-light text-ald-ivory">{value}</span>
      <span className="font-mono text-sm text-ald-text-dim">{label}</span>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
