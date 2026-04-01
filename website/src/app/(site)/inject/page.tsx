'use client';

import { useState, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const ACCEPTED_EXT = ['.jpg', '.jpeg', '.png', '.gif'];
const PROFILES = [
  { value: 'compound', label: 'Compound (all layers)', desc: 'Twin + Magic + Rare Basket + Halos + DQT' },
  { value: 'twin', label: 'Twin Markers', desc: 'Adjacent prime-gap pairs' },
  { value: 'magic', label: 'Magic Sentinel', desc: 'Prime-gap + B=42' },
  { value: 'single_rare', label: 'Rare Basket', desc: 'Grid-avoiding primes only' },
  { value: 'single_basic', label: 'Basic', desc: 'Minimal embedding' },
];

interface InjectResult {
  upload_group: string;
  image_hash: string;
  profile: string;
  total_markers: number;
  total_sentinels: number;
  layers_active: string[];
  mean_adjustment: number;
  max_adjustment: number;
  files: { file_id: number; file_type: string; file_name: string; file_size: number }[];
}

export default function InjectPage() {
  const { isAuthenticated, isLoading, getIdToken, signInWithGoogle } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [profile, setProfile] = useState('compound');
  const [seed, setSeed] = useState(42);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InjectResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function validateFile(f: File): string | null {
    if (!ACCEPTED_TYPES.includes(f.type)) return 'Invalid file type. Accepted: JPEG, PNG, GIF';
    const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPTED_EXT.includes(ext)) return 'Invalid file extension.';
    if (f.size > 50 * 1024 * 1024) return 'File too large (max 50 MB).';
    return null;
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const err = validateFile(f);
    if (err) { setError(err); setFile(null); setPreview(null); return; }
    setError(null); setFile(f); setResult(null);
    setPreview(URL.createObjectURL(f));
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    const err = validateFile(f);
    if (err) { setError(err); return; }
    setError(null); setFile(f); setResult(null);
    setPreview(URL.createObjectURL(f));
  }

  async function handleSubmit() {
    if (!file) return;
    setUploading(true); setError(null); setResult(null);

    try {
      const token = await getIdToken();
      const formData = new FormData();
      formData.append('image', file);
      formData.append('profile', profile);
      formData.append('seed', String(seed));

      const res = await fetch('/api/locker/inject', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const ct = res.headers.get('content-type') || '';
      if (!ct.includes('application/json')) {
        throw new Error(`Server error (${res.status}). The image may be too large or the server timed out.`);
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Injection failed');

      setResult(data);
      // Swap preview to the injected image
      const injectedFile = data.files?.find((f: { file_type: string }) => f.file_type === 'injected');
      if (injectedFile) {
        getIdToken().then((tk) =>
          fetch(`/api/locker/download?file_id=${injectedFile.file_id}`, {
            headers: { Authorization: `Bearer ${tk}` },
          })
        ).then((r) => r.blob()).then((blob) => {
          setPreview(URL.createObjectURL(blob));
        }).catch(() => {});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setUploading(false);
    }
  }

  async function downloadFile(fileId: number, fileName: string) {
    try {
      const token = await getIdToken();
      const res = await fetch(`/api/locker/download?file_id=${fileId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Download failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = fileName; a.click();
      URL.revokeObjectURL(url);
    } catch { setError('Download failed'); }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-ald-blue border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="ald-inject-wrapper mx-auto max-w-4xl px-6 py-12 text-center">
        <h1 className="mb-4 font-mono text-2xl font-light uppercase tracking-[0.12em] text-ald-ivory">Granite — Inject</h1>
        <p className="mb-6 font-mono text-sm text-ald-text-muted">Sign in to embed provenance signals into images.</p>
        <button onClick={signInWithGoogle}
          className="rounded border border-ald-blue/30 bg-ald-blue/10 px-6 py-3 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue hover:text-white transition-colors">
          Sign In with Google
        </button>
      </div>
    );
  }

  return (
    <div className="ald-inject-wrapper mx-auto max-w-4xl px-6 py-12">
      <div className="mb-8">
        <h1 className="mb-2 font-mono text-2xl font-light uppercase tracking-[0.12em] text-ald-ivory">
          Granite — Inject
        </h1>
        <p className="font-mono text-sm text-ald-text-muted">
          Embed provenance signals into an image
        </p>
      </div>

      {/* Upload area */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className="group mb-6 flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-stone-700 bg-stone-900 p-12 transition-colors hover:border-stone-500 hover:bg-stone-800"
      >
        <input ref={inputRef} type="file" accept=".jpg,.jpeg,.png,.gif" onChange={handleFileSelect} className="hidden" />
        {preview ? (
          <img src={preview} alt="Preview" className="mb-4 max-h-64 rounded-lg object-contain" />
        ) : (
          <div className="mb-4 text-4xl text-ald-text-dim">+</div>
        )}
        <p className="font-mono text-sm text-ald-text-muted group-hover:text-ald-text">
          {file ? file.name : 'Drop image here or click to select'}
        </p>
        <p className="mt-1 font-mono text-xs text-ald-text-dim">JPEG, PNG, GIF — max 50 MB</p>
      </div>

      {/* Controls */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-2 block font-mono text-xs uppercase tracking-wider text-ald-text-muted">Profile</label>
          <select
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            className="w-full rounded border border-ald-border bg-ald-surface px-3 py-2 font-mono text-sm text-ald-text focus:border-ald-blue focus:outline-none"
          >
            {PROFILES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
          <p className="mt-1 font-mono text-xs text-ald-text-dim">
            {PROFILES.find((p) => p.value === profile)?.desc}
          </p>
        </div>
        <div>
          <label className="mb-2 block font-mono text-xs uppercase tracking-wider text-ald-text-muted">Seed</label>
          <input
            type="number" value={seed} onChange={(e) => setSeed(parseInt(e.target.value) || 42)}
            className="w-full rounded border border-ald-border bg-ald-surface px-3 py-2 font-mono text-sm text-ald-text focus:border-ald-blue focus:outline-none"
          />
          <p className="mt-1 font-mono text-xs text-ald-text-dim">Position selection seed</p>
        </div>
      </div>

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!file || uploading}
        className="mb-8 w-full rounded border border-ald-blue/30 bg-ald-blue/10 px-6 py-3 font-mono text-sm uppercase tracking-wider text-ald-blue transition-colors hover:bg-ald-blue hover:text-ald-void disabled:cursor-not-allowed disabled:opacity-40"
      >
        {uploading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-ald-blue border-t-transparent" />
            Injecting...
          </span>
        ) : 'Inject Provenance Signal'}
      </button>

      {error && (
        <div className="mb-6 rounded border border-ald-red/30 bg-ald-red/5 p-4 font-mono text-sm text-ald-red">{error}</div>
      )}

      {/* Result */}
      {result && (
        <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
          <h2 className="mb-4 font-mono text-lg font-light uppercase tracking-wider text-ald-green">Injection Complete</h2>
          <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Markers" value={result.total_markers} />
            <Stat label="Sentinels" value={result.total_sentinels} />
            <Stat label="Mean Adj." value={`${result.mean_adjustment.toFixed(1)}px`} />
            <Stat label="Max Adj." value={`${result.max_adjustment}px`} />
          </div>
          <div className="mb-4">
            <span className="font-mono text-xs uppercase tracking-wider text-ald-text-muted">Active Layers</span>
            <div className="mt-1 flex flex-wrap gap-2">
              {result.layers_active.map((layer) => (
                <span key={layer} className="rounded border border-ald-blue/20 bg-ald-blue/5 px-2 py-0.5 font-mono text-xs text-ald-blue">{layer}</span>
              ))}
            </div>
          </div>
          <div className="mb-2"><span className="font-mono text-xs uppercase tracking-wider text-ald-text-muted">Downloads</span></div>
          <div className="space-y-2">
            {result.files.map((f) => (
              <button key={f.file_id} onClick={() => downloadFile(f.file_id, f.file_name)}
                className="group flex w-full items-center justify-between rounded border-2 border-ald-blue/30 bg-ald-blue/5 px-4 py-3 text-left transition-all hover:border-ald-blue hover:bg-ald-blue/15 active:scale-[0.99] cursor-pointer">
                <div className="flex items-center gap-3">
                  <svg className="h-5 w-5 shrink-0 text-ald-blue group-hover:translate-y-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3" />
                  </svg>
                  <div>
                    <span className="font-mono text-sm text-ald-text group-hover:text-ald-blue transition-colors">{f.file_name}</span>
                    <span className="ml-3 font-mono text-xs text-ald-text-dim">{formatFileType(f.file_type)}</span>
                  </div>
                </div>
                <span className="font-mono text-xs text-ald-blue/70">{formatBytes(f.file_size)}</span>
              </button>
            ))}
          </div>
          <p className="mt-4 font-mono text-xs text-ald-text-dim">Hash: {result.image_hash} — Group: {result.upload_group}</p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border border-ald-border bg-ald-deep p-3">
      <div className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">{label}</div>
      <div className="mt-1 font-mono text-lg text-ald-ivory">{value}</div>
    </div>
  );
}

function formatFileType(type: string): string {
  const labels: Record<string, string> = {
    injected: 'Injected (JPEG + DQT)',
    injected_png: 'Injected (PNG lossless)',
    heatmap: 'Heatmap',
    manifest: 'Manifest',
    histogram: 'Histogram',
  };
  return labels[type] || type;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
