'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

interface Note {
  note_id: number;
  title: string;
  body: string;
  source: string | null;
  tickers: string[];
  created_at: string;
  updated_at: string;
}

export default function NotesPage() {
  const { isAuthenticated, isLoading: authLoading, getIdToken } = useAuth();
  const router = useRouter();

  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editBody, setEditBody] = useState('');
  const [newTitle, setNewTitle] = useState('');
  const [newBody, setNewBody] = useState('');
  const [showNew, setShowNew] = useState(false);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) router.push('/alidade/login');
  }, [isAuthenticated, authLoading, router]);

  const fetchNotes = useCallback(async () => {
    const token = await getIdToken();
    if (!token) return;
    setLoading(true);
    const res = await fetch('/api/notes', { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      const data = await res.json();
      setNotes(data.notes);
    }
    setLoading(false);
  }, [getIdToken]);

  useEffect(() => { if (isAuthenticated) fetchNotes(); }, [fetchNotes, isAuthenticated]);

  async function saveEdit() {
    if (!editingId) return;
    const token = await getIdToken();
    if (!token) return;
    await fetch('/api/notes', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ note_id: editingId, title: editTitle, body: editBody }),
    });
    setEditingId(null);
    fetchNotes();
  }

  async function deleteNote(noteId: number) {
    if (!confirm('Delete this note?')) return;
    const token = await getIdToken();
    if (!token) return;
    await fetch('/api/notes', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ note_id: noteId }),
    });
    fetchNotes();
  }

  async function createNote() {
    if (!newTitle.trim()) return;
    const token = await getIdToken();
    if (!token) return;
    await fetch('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ title: newTitle.trim(), body: newBody }),
    });
    setNewTitle('');
    setNewBody('');
    setShowNew(false);
    fetchNotes();
  }

  if (authLoading || (!isAuthenticated && !authLoading)) {
    return (
      <div className="flex min-h-[calc(100vh-57px)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-2xl font-light tracking-tight text-ald-ivory">My Notes</h1>
          <p className="text-sm text-ald-text-muted">
            {loading ? 'Loading...' : `${notes.length} notes`}
          </p>
        </div>
        <button
          onClick={() => { setShowNew(true); setNewTitle(''); setNewBody(''); }}
          className="rounded border border-ald-blue/40 bg-ald-blue/10 px-4 py-2 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue/20 transition-colors"
        >
          + New Note
        </button>
      </div>

      {/* New note form */}
      {showNew && (
        <div className="mb-6 rounded-lg border border-ald-blue/30 bg-ald-surface p-4">
          <input
            type="text"
            placeholder="Title..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            autoFocus
            className="w-full mb-2 rounded border border-ald-border bg-ald-void px-3 py-2 font-mono text-sm text-ald-text placeholder:text-ald-text-dim focus:border-ald-blue/40 focus:outline-none"
          />
          <textarea
            placeholder="Notes..."
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            rows={3}
            className="w-full mb-3 rounded border border-ald-border bg-ald-void px-3 py-2 font-mono text-xs text-ald-text placeholder:text-ald-text-dim focus:border-ald-blue/40 focus:outline-none resize-y"
          />
          <div className="flex gap-2">
            <button onClick={() => setShowNew(false)} className="rounded border border-ald-border px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors">Cancel</button>
            <button onClick={createNote} disabled={!newTitle.trim()} className="rounded bg-ald-blue/20 border border-ald-blue/40 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-blue hover:bg-ald-blue/30 transition-colors disabled:opacity-30">Save</button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ald-border border-t-ald-blue" />
        </div>
      ) : notes.length === 0 ? (
        <div className="rounded-lg border border-ald-border bg-ald-surface p-12 text-center">
          <p className="text-sm text-ald-text-muted mb-2">No notes yet.</p>
          <p className="font-mono text-xs text-ald-text-dim">
            Save comparisons from the bartender, or create your own.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {notes.map((n) => (
            <div key={n.note_id} className="rounded-lg border border-ald-border bg-ald-surface p-4">
              {editingId === n.note_id ? (
                <div>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full mb-2 rounded border border-ald-border bg-ald-void px-3 py-2 font-mono text-sm text-ald-text focus:border-ald-blue/40 focus:outline-none"
                  />
                  <textarea
                    value={editBody}
                    onChange={(e) => setEditBody(e.target.value)}
                    rows={4}
                    className="w-full mb-3 rounded border border-ald-border bg-ald-void px-3 py-2 font-mono text-xs text-ald-text focus:border-ald-blue/40 focus:outline-none resize-y"
                  />
                  <div className="flex gap-2">
                    <button onClick={() => setEditingId(null)} className="rounded border border-ald-border px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-text-dim hover:text-ald-text transition-colors">Cancel</button>
                    <button onClick={saveEdit} className="rounded bg-ald-blue/20 border border-ald-blue/40 px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ald-blue hover:bg-ald-blue/30 transition-colors">Save</button>
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <span className="block font-mono text-sm text-ald-ivory">{n.title}</span>
                      <span className="font-mono text-[10px] text-ald-text-dim">
                        {new Date(n.updated_at).toLocaleDateString()} {new Date(n.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        {n.source && <span className="ml-2 rounded bg-ald-surface-2 px-1.5 py-px text-ald-text-dim">{n.source}</span>}
                      </span>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => { setEditingId(n.note_id); setEditTitle(n.title); setEditBody(n.body); }}
                        className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim hover:text-ald-blue transition-colors"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteNote(n.note_id)}
                        className="font-mono text-[10px] uppercase tracking-wider text-ald-text-dim hover:text-ald-red transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  {n.body && (
                    <p className="text-xs text-ald-text-dim whitespace-pre-wrap">{n.body}</p>
                  )}
                  {n.tickers.length > 0 && (
                    <div className="mt-2 flex gap-1">
                      {n.tickers.map((t) => (
                        <Link
                          key={t}
                          href={`/alidade/research/${t}`}
                          className="rounded bg-ald-surface-2 px-2 py-0.5 font-mono text-[10px] text-ald-blue hover:text-ald-ivory transition-colors"
                        >
                          {t}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
