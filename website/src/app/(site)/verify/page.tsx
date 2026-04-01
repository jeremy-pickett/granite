'use client';

import { useState, useRef } from 'react';
import { useAuth } from '@/contexts/AuthContext';

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/gif'];
const ACCEPTED_EXT = ['.jpg', '.jpeg', '.png', '.gif'];

interface CheckResult {
  detected?: boolean;
  applicable?: boolean;
  [key: string]: unknown;
}

interface VerifyResult {
  image_name: string;
  image_hash: string;
  width: number;
  height: number;
  verdict: string;
  confidence: string;
  signals_detected: string[];
  signal_count: number;
  checks: Record<string, CheckResult>;
}

const CHECK_LABELS: Record<string, { name: string; desc: string }> = {
  dqt_primes: { name: 'DQT Prime Tables', desc: 'Layer 1 — quantization table entries shifted to primes' },
  prime_enrichment: { name: 'Prime Enrichment', desc: 'Layer 2 — elevated prime-gap hit rate at grid positions' },
  twin_pairs: { name: 'Twin Pairs', desc: 'Layer 2 — adjacent pixel pairs both with prime R-G distances' },
  magic_sentinels: { name: 'Magic Sentinels', desc: 'Layer 2+ — B=42 adjacent to prime-gap positions' },
  mersenne_sentinels: { name: 'Mersenne Sentinels', desc: 'Structural — Mersenne prime bracketing (corroborating)' },
  radial_halos: { name: 'Radial Halos', desc: 'Layer 3 — two-zone radial lensing halo centers' },
};

const VERDICT_STYLES: Record<string, string> = {
  CONFIRMED: 'text-ald-green border-ald-green/30 bg-ald-green/5',
  PROBABLE: 'text-ald-cyan border-ald-cyan/30 bg-ald-cyan/5',
  PARTIAL: 'text-ald-amber border-ald-amber/30 bg-ald-amber/5',
  'NOT DETECTED': 'text-ald-text-dim border-ald-border bg-ald-deep',
};

export default function VerifyPage() {
  const { isAuthenticated, isLoading, getIdToken, signInWithGoogle } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResult | null>(null);
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

      const res = await fetch('/api/locker/verify', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const ct = res.headers.get('content-type') || '';
      if (!ct.includes('application/json')) {
        throw new Error(`Server error (${res.status}). The image may be too large or the server timed out.`);
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Verification failed');

      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setUploading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-ald-cyan border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="ald-inject-wrapper mx-auto max-w-4xl px-6 py-12 text-center">
        <h1 className="mb-4 font-mono text-2xl font-light uppercase tracking-[0.12em] text-ald-ivory">Granite — Verify</h1>
        <p className="mb-6 font-mono text-sm text-ald-text-muted">Sign in to scan images for provenance signals.</p>
        <button onClick={signInWithGoogle}
          className="rounded border border-ald-cyan/30 bg-ald-cyan/10 px-6 py-3 font-mono text-sm uppercase tracking-wider text-ald-cyan hover:bg-ald-cyan hover:text-white transition-colors">
          Sign In with Google
        </button>
      </div>
    );
  }

  return (
    <div className="ald-inject-wrapper mx-auto max-w-4xl px-6 py-12">
      <div className="mb-8">
        <h1 className="mb-2 font-mono text-2xl font-light uppercase tracking-[0.12em] text-ald-ivory">
          Granite — Verify
        </h1>
        <p className="font-mono text-sm text-ald-text-muted">
          Scan an image for provenance signals
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
          <div className="mb-4 text-4xl text-ald-text-dim">?</div>
        )}
        <p className="font-mono text-sm text-ald-text-muted group-hover:text-ald-text">
          {file ? file.name : 'Drop image here or click to select'}
        </p>
        <p className="mt-1 font-mono text-xs text-ald-text-dim">JPEG, PNG, GIF — max 50 MB</p>
      </div>

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!file || uploading}
        className="mb-8 w-full rounded border border-ald-cyan/30 bg-ald-cyan/10 px-6 py-3 font-mono text-sm uppercase tracking-wider text-ald-cyan transition-colors hover:bg-ald-cyan hover:text-ald-void disabled:cursor-not-allowed disabled:opacity-40"
      >
        {uploading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="h-4 w-4 animate-spin rounded-full border-2 border-ald-cyan border-t-transparent" />
            Scanning...
          </span>
        ) : 'Verify Provenance Signal'}
      </button>

      {error && (
        <div className="mb-6 rounded border border-ald-red/30 bg-ald-red/5 p-4 font-mono text-sm text-ald-red">{error}</div>
      )}

      {/* Result */}
      {result && (
        <div className="space-y-6">
          <div className={`rounded-lg border p-6 text-center ${VERDICT_STYLES[result.verdict] || VERDICT_STYLES['NOT DETECTED']}`}>
            <div className="font-mono text-xs uppercase tracking-widest opacity-60">Verdict</div>
            <div className="mt-1 font-mono text-3xl font-light uppercase tracking-wider">{result.verdict}</div>
            <div className="mt-1 font-mono text-sm opacity-70">
              {result.confidence} confidence — {result.signal_count} signal{result.signal_count !== 1 ? 's' : ''} detected
            </div>
          </div>

          <div className="flex items-center gap-6 rounded border border-ald-border bg-ald-surface p-4">
            <div><span className="font-mono text-xs text-ald-text-dim">Image</span><div className="font-mono text-sm text-ald-text">{result.image_name}</div></div>
            <div><span className="font-mono text-xs text-ald-text-dim">Size</span><div className="font-mono text-sm text-ald-text">{result.width} x {result.height}</div></div>
            <div><span className="font-mono text-xs text-ald-text-dim">Hash</span><div className="font-mono text-sm text-ald-text">{result.image_hash}</div></div>
          </div>

          <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
            <h2 className="mb-4 font-mono text-sm uppercase tracking-wider text-ald-text-muted">Signal Checks</h2>
            <div className="space-y-3">
              {Object.entries(result.checks).map(([key, check]) => {
                const info = CHECK_LABELS[key] || { name: key, desc: '' };
                const isNA = check.applicable === false;
                const detected = check.detected === true;
                return (
                  <div key={key} className="flex items-start justify-between rounded border border-ald-border bg-ald-deep px-4 py-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`inline-block h-2 w-2 rounded-full ${isNA ? 'bg-ald-text-dim' : detected ? 'bg-ald-green' : 'bg-ald-red/60'}`} />
                        <span className="font-mono text-sm text-ald-text">{info.name}</span>
                      </div>
                      <p className="ml-4 mt-0.5 font-mono text-xs text-ald-text-dim">{info.desc}</p>
                    </div>
                    <span className={`shrink-0 font-mono text-xs uppercase tracking-wider ${isNA ? 'text-ald-text-dim' : detected ? 'text-ald-green' : 'text-ald-red/60'}`}>
                      {isNA ? 'N/A' : detected ? 'Detected' : 'Not Found'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Detail panels */}
          {result.checks.prime_enrichment && (result.checks.prime_enrichment as Record<string, unknown>).prime_hit_rate !== undefined && (
            <DetailPanel title="Prime Enrichment Detail" items={[
              { label: 'Hit Rate', value: `${((result.checks.prime_enrichment as Record<string, number>).prime_hit_rate * 100).toFixed(1)}%` },
              { label: 'Basket Rate', value: `${((result.checks.prime_enrichment as Record<string, number>).basket_hit_rate * 100).toFixed(2)}%` },
              { label: 'Positions', value: String((result.checks.prime_enrichment as Record<string, number>).n_positions) },
              { label: 'Grid Phase', value: String((result.checks.prime_enrichment as Record<string, string>).grid_phase || '\u2014') },
            ]} />
          )}
          {result.checks.twin_pairs && (result.checks.twin_pairs as Record<string, unknown>).twin_rate !== undefined && (
            <DetailPanel title="Twin Pair Detail" items={[
              { label: 'Twin Rate', value: `${((result.checks.twin_pairs as Record<string, number>).twin_rate * 100).toFixed(2)}%` },
              { label: 'Twin Hits', value: String((result.checks.twin_pairs as Record<string, number>).twin_hits) },
              { label: 'Checked', value: String((result.checks.twin_pairs as Record<string, number>).total_checked) },
              { label: 'Grid Phase', value: String((result.checks.twin_pairs as Record<string, string>).grid_phase || '\u2014') },
            ]} />
          )}
        </div>
      )}
    </div>
  );
}

function DetailPanel({ title, items }: { title: string; items: { label: string; value: string }[] }) {
  return (
    <div className="rounded-lg border border-ald-border bg-ald-surface p-6">
      <h2 className="mb-3 font-mono text-sm uppercase tracking-wider text-ald-text-muted">{title}</h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {items.map((item) => (
          <div key={item.label} className="rounded border border-ald-border bg-ald-deep p-3">
            <div className="font-mono text-xs uppercase tracking-wider text-ald-text-dim">{item.label}</div>
            <div className="mt-1 font-mono text-sm text-ald-ivory">{item.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
