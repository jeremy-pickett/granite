'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { usePortfolio } from '@/hooks/usePortfolio';
import CompareOverlay, { type CompareSecurity } from '@/components/alidade/securities/CompareOverlay';
import IALDScoreGauge from '@/components/alidade/securities/IALDScoreGauge';

// ─── Types ───────────────────────────────────────────────────────────────────

interface Cohort {
  cohort_id: number;
  cohort_type: string;
  cohort_name: string;
  description: string;
  user_id: number | null;
  member_count: number;
}

interface Member {
  security_id: number;
  ticker: string;
  name: string;
  security_type: string;
  iald: number | null;
  verdict: string | null;
}

// ─── Logo circle component ──────────────────────────────────────────────────

function LogoCircle({ ticker, offset }: { ticker: string; offset: number }) {
  const [err, setErr] = useState(false);
  const style = { marginLeft: offset === 0 ? 0 : -10, zIndex: 50 - offset };

  if (err) {
    return (
      <div
        className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ald-surface-2 border-2 border-ald-void font-mono text-[10px] text-ald-text-dim"
        style={style}
        title={ticker}
      >
        {ticker.slice(0, 2)}
      </div>
    );
  }
  return (
    <Image
      src={`/logos/${ticker}.png`}
      alt={ticker}
      width={36}
      height={36}
      className="relative inline-block h-9 w-9 shrink-0 rounded-full border-2 border-ald-void object-cover"
      style={style}
      title={ticker}
      onError={() => setErr(true)}
    />
  );
}

function OverflowCount({ count }: { count: number }) {
  return (
    <div
      className="relative inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ald-surface-2 border-2 border-ald-void font-mono text-[10px] text-ald-text-dim"
      style={{ marginLeft: -10 }}
    >
      +{count}
    </div>
  );
}

// ─── Score color helper ─────────────────────────────────────────────────────

function verdictColor(verdict: string | null): string {
  if (!verdict) return 'text-ald-text-dim';
  if (verdict === 'CRITICAL') return 'text-ald-red';
  if (verdict === 'ELEVATED') return 'text-ald-amber';
  if (verdict === 'MODERATE') return 'text-ald-blue';
  return 'text-ald-text-dim';
}

// ─── Main Page ───────────────────────────────────────────────────────────────

export default function CohortsPage() {
  const { isAuthenticated, isLoading: authLoading, getIdToken } = useAuth();
  const router = useRouter();
  const { glowClass } = usePortfolio();

  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [loading, setLoading] = useState(true);

  // Selected cohort detail
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedCohort, setSelectedCohort] = useState<Cohort | null>(null);
  const [membersLoading, setMembersLoading] = useState(false);

  // Create dialog
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [createStep, setCreateStep] = useState<'name' | 'loading' | 'review'>('name');
  const [suggestedTickers, setSuggestedTickers] = useState<string[]>([]);

  // Add member
  const [addTicker, setAddTicker] = useState('');
  const [addLoading, setAddLoading] = useState(false);

  // Deleting
  const [deleting, setDeleting] = useState<number | null>(null);

  // Sort
  const [sortBy, setSortBy] = useState<'ticker' | 'name' | 'iald_desc' | 'iald_asc'>('ticker');

  // Drag-to-compare state
  const [dragSource, setDragSource] = useState<Member | null>(null);
  const [dropTarget, setDropTarget] = useState<number | null>(null);
  const [compareLeft, setCompareLeft] = useState<CompareSecurity | null>(null);
  const [compareRight, setCompareRight] = useState<CompareSecurity | null>(null);
  const dragGhostRef = useRef<HTMLDivElement>(null);

  // Auth guard
  useEffect(() => {
    if (!authLoading && !isAuthenticated) router.push('/alidade/login');
  }, [isAuthenticated, authLoading, router]);

  // Fetch cohorts
  const fetchCohorts = useCallback(async () => {
    const token = await getIdToken();
    setLoading(true);
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch('/api/cohorts', { headers });
    if (res.ok) {
      const data = await res.json();
      setCohorts(data.cohorts);
    }
    setLoading(false);
  }, [getIdToken]);

  useEffect(() => { if (isAuthenticated) fetchCohorts(); }, [fetchCohorts, isAuthenticated]);

  // Fetch members for selected cohort
  const fetchMembers = useCallback(async (cohortId: number) => {
    setMembersLoading(true);
    const res = await fetch(`/api/cohorts/members?cohort_id=${cohortId}`);
    if (res.ok) {
      const data = await res.json();
      setMembers(data.members);
      setSelectedCohort(data.cohort);
    }
    setMembersLoading(false);
  }, []);

  function selectCohort(c: Cohort) {
    setSelectedId(c.cohort_id);
    fetchMembers(c.cohort_id);
  }

  // ─── Create flow ─────────────────────────────────────────────────────

  async function startCreate() {
    if (!newName.trim()) return;
    setCreateStep('loading');

    const token = await getIdToken();
    if (!token) return;

    // Ask AI for suggestions
    try {
      const res = await fetch('/api/cohorts/suggest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ cohort_name: newName.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        setSuggestedTickers(data.tickers ?? []);
      }
    } catch {}

    setCreateStep('review');
  }

  function removeSuggested(ticker: string) {
    setSuggestedTickers(suggestedTickers.filter(t => t !== ticker));
  }

  async function confirmCreate() {
    const token = await getIdToken();
    if (!token) return;

    const res = await fetch('/api/cohorts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        cohort_name: newName.trim(),
        description: '',
        tickers: suggestedTickers,
      }),
    });

    if (res.ok) {
      const data = await res.json();
      setShowCreate(false);
      setNewName('');
      setCreateStep('name');
      setSuggestedTickers([]);
      await fetchCohorts();
      // Auto-select the new cohort
      selectCohort({ cohort_id: data.cohort_id, cohort_type: 'user', cohort_name: newName.trim(), description: '', user_id: null, member_count: suggestedTickers.length });
    }
  }

  // ─── Add/Remove members ──────────────────────────────────────────────

  async function addMember() {
    if (!addTicker.trim() || !selectedId) return;
    const token = await getIdToken();
    if (!token) return;
    setAddLoading(true);

    const res = await fetch('/api/cohorts/members', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ cohort_id: selectedId, ticker: addTicker.trim() }),
    });

    if (res.ok) {
      setAddTicker('');
      fetchMembers(selectedId);
      fetchCohorts();
    }
    setAddLoading(false);
  }

  async function removeMember(ticker: string) {
    if (!selectedId) return;
    const token = await getIdToken();
    if (!token) return;

    await fetch('/api/cohorts/members', {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ cohort_id: selectedId, ticker }),
    });

    fetchMembers(selectedId);
    fetchCohorts();
  }

  async function deleteCohort(cohortId: number) {
    if (!confirm('Delete this cohort?')) return;
    const token = await getIdToken();
    if (!token) return;
    setDeleting(cohortId);

    await fetch('/api/cohorts', {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ cohort_id: cohortId }),
    });

    if (selectedId === cohortId) {
      setSelectedId(null);
      setMembers([]);
      setSelectedCohort(null);
    }
    setDeleting(null);
    fetchCohorts();
  }

  // Close compare on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setCompareLeft(null);
        setCompareRight(null);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Drag handlers
  function onDragStart(e: React.DragEvent, m: Member) {
    setDragSource(m);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', m.ticker);
    if (dragGhostRef.current) {
      dragGhostRef.current.textContent = m.ticker;
      e.dataTransfer.setDragImage(dragGhostRef.current, 30, 16);
    }
  }

  function onDragOver(e: React.DragEvent, securityId: number) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDropTarget(securityId);
  }

  function onDragLeave() {
    setDropTarget(null);
  }

  function onDrop(e: React.DragEvent, target: Member) {
    e.preventDefault();
    setDropTarget(null);
    if (dragSource && dragSource.security_id !== target.security_id) {
      setCompareLeft(dragSource as CompareSecurity);
      setCompareRight(target as CompareSecurity);
    }
    setDragSource(null);
  }

  function onDragEnd() {
    setDragSource(null);
    setDropTarget(null);
  }

  // Sort members
  function sortedMembers(list: Member[]): Member[] {
    const copy = [...list];
    switch (sortBy) {
      case 'ticker':
        return copy.sort((a, b) => a.ticker.localeCompare(b.ticker));
      case 'name':
        return copy.sort((a, b) => a.name.localeCompare(b.name));
      case 'iald_desc':
        return copy.sort((a, b) => (b.iald ?? -1) - (a.iald ?? -1));
      case 'iald_asc':
        return copy.sort((a, b) => (a.iald ?? 999) - (b.iald ?? 999));
      default:
        return copy;
    }
  }

  // ─── Render ───────────────────────────────────────────────────────────

  if (authLoading || (!isAuthenticated && !authLoading)) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  const isOwner = selectedCohort?.user_id !== null && selectedCohort?.user_id !== undefined;

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Invisible drag ghost */}
      <div
        ref={dragGhostRef}
        className="fixed -left-[9999px] rounded bg-ald-blue px-3 py-1 font-mono text-sm text-ald-void"
      />

      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-light tracking-tight text-ald-ivory">Cohorts</h1>
          <p className="text-sm text-ald-text-muted">
            {loading ? 'Loading...' : `${cohorts.length} cohorts`}
          </p>
        </div>
        <button
          onClick={() => { setShowCreate(true); setCreateStep('name'); setNewName(''); setSuggestedTickers([]); }}
          className="rounded border border-ald-blue/40 bg-ald-blue/10 px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue/20 transition-colors"
        >
          + New Cohort
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left: Cohort list */}
        <div className="lg:col-span-1 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
            </div>
          ) : cohorts.length === 0 ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-8 text-center">
              <p className="text-sm text-ald-text-muted mb-2">No cohorts yet.</p>
              <p className="font-mono text-xs text-ald-text-dim">Create one to get started.</p>
            </div>
          ) : (
            cohorts.map((c) => (
              <button
                key={c.cohort_id}
                onClick={() => selectCohort(c)}
                className={`w-full text-left rounded-lg border p-4 transition-all ${
                  selectedId === c.cohort_id
                    ? 'border-ald-blue/40 bg-ald-blue/10'
                    : 'border-ald-border bg-ald-surface hover:border-ald-blue/30'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-sm text-ald-ivory">{c.cohort_name}</span>
                  <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">
                    {c.cohort_type}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs text-ald-text-dim">
                    {c.member_count} {c.member_count === 1 ? 'security' : 'securities'}
                  </span>
                  {c.user_id && (
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteCohort(c.cohort_id); }}
                      disabled={deleting === c.cohort_id}
                      className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim hover:text-ald-red transition-colors"
                    >
                      {deleting === c.cohort_id ? '...' : 'Delete'}
                    </button>
                  )}
                </div>
              </button>
            ))
          )}
        </div>

        {/* Right: Cohort detail */}
        <div className="lg:col-span-2">
          {!selectedId ? (
            <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
              <p className="text-sm text-ald-text-muted">Select a cohort to view its members.</p>
            </div>
          ) : membersLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
            </div>
          ) : (
            <div>
              {/* Cohort header with overlapping logos */}
              <div className="mb-6 rounded-lg border border-ald-border bg-ald-surface p-6">
                <h2 className="font-mono text-lg text-ald-ivory mb-2">
                  {selectedCohort?.cohort_name}
                </h2>
                <div className="flex items-center mb-4">
                  {members.slice(0, 12).map((m, i) => (
                    <Link href={`/alidade/research/${m.ticker}`} key={m.ticker}>
                      <LogoCircle ticker={m.ticker} offset={i} />
                    </Link>
                  ))}
                  {members.length > 12 && <OverflowCount count={members.length - 12} />}
                </div>
                <span className="font-mono text-xs text-ald-text-dim">
                  {members.length} {members.length === 1 ? 'security' : 'securities'}
                </span>
              </div>

              {/* Add member (only for user cohorts) */}
              {isOwner && (
                <div className="mb-4 flex gap-2">
                  <input
                    type="text"
                    placeholder="Add ticker..."
                    value={addTicker}
                    onChange={(e) => setAddTicker(e.target.value.toUpperCase())}
                    onKeyDown={(e) => { if (e.key === 'Enter') addMember(); }}
                    className="rounded border border-ald-border bg-ald-surface px-4 py-2 font-mono text-sm text-ald-text placeholder:text-ald-text-dim focus:border-ald-blue/40 focus:outline-none w-40"
                  />
                  <button
                    onClick={addMember}
                    disabled={addLoading || !addTicker.trim()}
                    className="rounded border border-ald-blue/40 bg-ald-blue/10 px-4 py-2 font-mono text-xs uppercase tracking-wider text-ald-blue hover:bg-ald-blue/20 transition-colors disabled:opacity-30"
                  >
                    {addLoading ? '...' : 'Add'}
                  </button>
                </div>
              )}

              {/* Sort control */}
              {members.length > 0 && (
                <div className="mb-4 flex items-center gap-2">
                  <label className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">Sort</label>
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                    className="rounded border border-ald-border bg-ald-surface px-3 py-1.5 font-mono text-xs text-ald-text focus:border-ald-blue/40 focus:outline-none"
                  >
                    <option value="ticker">Ticker A-Z</option>
                    <option value="name">Name</option>
                    <option value="iald_desc">IALD High → Low</option>
                    <option value="iald_asc">IALD Low → High</option>
                  </select>
                </div>
              )}

              {/* Members list */}
              {members.length === 0 ? (
                <div className="rounded-lg border border-ald-border bg-ald-surface p-8 text-center">
                  <p className="text-sm text-ald-text-muted">No members in this cohort yet.</p>
                </div>
              ) : (
                <div className="grid gap-2 md:grid-cols-2">
                  {sortedMembers(members).map((m) => {
                    const isDragOver = dropTarget === m.security_id;
                    const isDragging = dragSource?.security_id === m.security_id;
                    const glow = glowClass(m.ticker);

                    return (
                      <div
                        key={m.security_id}
                        draggable
                        onDragStart={(e) => onDragStart(e, m)}
                        onDragOver={(e) => onDragOver(e, m.security_id)}
                        onDragLeave={onDragLeave}
                        onDrop={(e) => onDrop(e, m)}
                        onDragEnd={onDragEnd}
                        className={`group relative flex items-center justify-between rounded-lg border bg-ald-surface p-3 transition-all cursor-grab active:cursor-grabbing ${glow} ${
                          isDragOver
                            ? 'ring-2 ring-ald-blue scale-[1.01] border-ald-blue/40'
                            : isDragging
                              ? 'opacity-50 scale-[0.98] border-ald-border'
                              : 'border-ald-border hover:border-ald-blue/30'
                        }`}
                      >
                        <Link
                          href={`/alidade/research/${m.ticker}`}
                          className="flex items-center gap-3 flex-1 min-w-0"
                          draggable={false}
                          onClick={(e) => { if (dragSource) e.preventDefault(); }}
                        >
                          <LogoCircle ticker={m.ticker} offset={0} />
                          <IALDScoreGauge
                            score={m.iald !== null ? Number(m.iald) : null}
                            size="sm"
                            showVerdict={false}
                          />
                          <div className="min-w-0">
                            <span className="block font-mono text-sm text-ald-ivory group-hover:text-ald-blue transition-colors">
                              {m.ticker}
                            </span>
                            <span className="block text-xs text-ald-text-dim truncate">{m.name}</span>
                          </div>
                        </Link>
                        <div className="flex items-center gap-4 shrink-0 ml-4">
                          {m.iald !== null && (
                            <span className={`font-mono text-sm ${verdictColor(m.verdict)}`}>
                              {Number(m.iald).toFixed(2)}
                            </span>
                          )}
                          {m.verdict && (
                            <span className={`font-mono text-[10px] uppercase tracking-wider ${verdictColor(m.verdict)}`}>
                              {m.verdict}
                            </span>
                          )}
                          <span className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-ald-text-dim">
                            {m.security_type}
                          </span>
                          {isOwner && (
                            <button
                              onClick={() => removeMember(m.ticker)}
                              className="font-mono text-xs text-ald-text-dim hover:text-ald-red transition-colors"
                            >
                              &times;
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Compare Overlay */}
      {compareLeft && compareRight && (
        <CompareOverlay
          left={compareLeft}
          right={compareRight}
          onClose={() => {
            setCompareLeft(null);
            setCompareRight(null);
          }}
        />
      )}

      {/* ─── Create Cohort Modal ─────────────────────────────────────────── */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-lg border border-ald-border bg-ald-void p-6 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-mono text-lg text-ald-ivory">New Cohort</h2>
              <button
                onClick={() => { setShowCreate(false); setCreateStep('name'); }}
                className="font-mono text-sm text-ald-text-dim hover:text-ald-text"
              >
                &times;
              </button>
            </div>

            {/* Step 1: Name */}
            {createStep === 'name' && (
              <div>
                <p className="text-sm text-ald-text-muted mb-4">
                  Give your cohort a descriptive name. Be specific — our AI will use this to suggest which securities belong.
                </p>
                <input
                  type="text"
                  placeholder='e.g. "Companies with auditor changes in 2026"'
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && newName.trim()) startCreate(); }}
                  autoFocus
                  className="w-full rounded border border-ald-border bg-ald-surface px-4 py-3 font-mono text-sm text-ald-text placeholder:text-ald-text-dim focus:border-ald-blue/40 focus:outline-none mb-4"
                />
                <div className="flex gap-3">
                  <button
                    onClick={() => setShowCreate(false)}
                    className="flex-1 rounded border border-ald-border py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={startCreate}
                    disabled={!newName.trim()}
                    className="flex-1 rounded bg-ald-blue/20 border border-ald-blue/40 py-2 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue/30 transition-colors disabled:opacity-30"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: AI Loading */}
            {createStep === 'loading' && (
              <div className="py-12 text-center">
                <div className="mb-4 flex justify-center">
                  <div className="h-10 w-10 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
                </div>
                <p className="font-mono text-sm text-ald-text-dim mb-1">
                  Analyzing securities...
                </p>
                <p className="text-xs text-ald-text-dim">
                  Matching &ldquo;{newName}&rdquo; against {cohorts.length > 0 ? 'the full universe' : 'all securities'}
                </p>
              </div>
            )}

            {/* Step 3: Review suggestions */}
            {createStep === 'review' && (
              <div>
                <p className="text-sm text-ald-text-muted mb-3">
                  {suggestedTickers.length > 0
                    ? `AI suggested ${suggestedTickers.length} securities for "${newName}". Remove any that don't belong.`
                    : `No AI suggestions available. You can create the cohort empty and add securities manually.`
                  }
                </p>

                {suggestedTickers.length > 0 && (
                  <div className="mb-4 rounded-lg border border-ald-border bg-ald-surface p-4 max-h-64 overflow-y-auto">
                    <div className="flex flex-wrap gap-2">
                      {suggestedTickers.map((ticker) => (
                        <div
                          key={ticker}
                          className="flex items-center gap-1 rounded-full border border-ald-border bg-ald-void pl-1 pr-2 py-1"
                        >
                          <LogoCircle ticker={ticker} offset={0} />
                          <span className="font-mono text-xs text-ald-ivory">{ticker}</span>
                          <button
                            onClick={() => removeSuggested(ticker)}
                            className="ml-1 font-mono text-xs text-ald-text-dim hover:text-ald-red transition-colors"
                          >
                            &times;
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex gap-3">
                  <button
                    onClick={() => setCreateStep('name')}
                    className="flex-1 rounded border border-ald-border py-2 font-mono text-sm uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors"
                  >
                    Back
                  </button>
                  <button
                    onClick={confirmCreate}
                    className="flex-1 rounded bg-ald-blue/20 border border-ald-blue/40 py-2 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue/30 transition-colors"
                  >
                    Create Cohort
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
