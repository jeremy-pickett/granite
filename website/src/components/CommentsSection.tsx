'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '@/contexts/AuthContext';

interface Comment {
  comment_id: number;
  body: string;
  author_name: string;
  is_authenticated: boolean;
  created_at: string;
}

interface Props {
  entityType: string;
  entityId: string;
  /** Visual variant: 'dark' for Granite/.plan pages, 'light' for Alidade pages */
  variant?: 'dark' | 'light';
  /** Cookie key for storing collapse preference */
  prefsKey?: string;
}

const PAGE_SIZE = 20;

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string) {
  const expires = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; expires=${expires}; SameSite=Lax`;
}

export default function CommentsSection({ entityType, entityId, variant = 'dark', prefsKey }: Props) {
  const { isAuthenticated, dbUser, getIdToken } = useAuth();
  const isAdmin = dbUser?.role === 'admin';

  const collapseKey = prefsKey ? `comments_collapsed_${prefsKey}` : null;
  const [collapsed, setCollapsed] = useState(() => {
    if (!collapseKey) return false;
    return getCookie(collapseKey) === '1';
  });

  const [comments, setComments] = useState<Comment[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);

  const [body, setBody] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState('');
  const [savedNoteId, setSavedNoteId] = useState<number | null>(null);
  const [dupNoteId, setDupNoteId] = useState<number | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const fetchComments = useCallback(async (p: number, append = false) => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/comments?entity_type=${entityType}&entity_id=${entityId}&page=${p}&limit=${PAGE_SIZE}`
      );
      if (res.ok) {
        const data = await res.json();
        setComments(prev => append ? [...prev, ...data.comments] : data.comments);
        setTotal(data.total);
        setHasMore(data.has_more);
        setPage(p);
      }
    } catch {}
    setLoading(false);
  }, [entityType, entityId]);

  useEffect(() => { fetchComments(1); }, [fetchComments]);

  function toggleCollapse() {
    const next = !collapsed;
    setCollapsed(next);
    if (collapseKey) setCookie(collapseKey, next ? '1' : '0');
  }

  async function handleSubmit() {
    if (!body.trim() || posting) return;
    setPosting(true);
    setError('');

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    try {
      const token = await getIdToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch {}

    const res = await fetch('/api/comments', {
      method: 'POST',
      headers,
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId, body: body }),
    });

    if (res.ok) {
      const comment = await res.json();
      setComments(prev => [comment, ...prev]);
      setTotal(prev => prev + 1);
      setBody('');
    } else if (res.status === 409) {
      setError('You already posted this comment');
    } else {
      const err = await res.json().catch(() => ({ error: 'Failed to post' }));
      setError(err.error || 'Failed to post');
    }
    setPosting(false);
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
    });
  }

  // Style maps for dark (Granite/.plan) vs light (Alidade)
  const s = variant === 'light' ? {
    border: 'border-ald-border',
    bg: 'bg-ald-surface',
    bgDeep: 'bg-ald-deep',
    text: 'text-ald-text',
    textDim: 'text-ald-text-dim',
    textMuted: 'text-ald-text-muted',
    heading: 'text-ald-ivory',
    input: 'border-ald-border bg-ald-deep text-ald-text placeholder:text-ald-text-dim focus:border-ald-blue/50',
    btn: 'bg-ald-surface-2 text-ald-text-dim hover:text-ald-text',
    commentBg: 'bg-ald-surface',
    commentBorder: 'border-ald-border',
    authed: 'text-ald-text',
    anon: 'text-ald-text-dim italic',
    prose: 'text-ald-text-muted',
  } : {
    border: 'border-stone-800',
    bg: 'bg-stone-900/20',
    bgDeep: 'bg-stone-900/30',
    text: 'text-stone-300',
    textDim: 'text-stone-600',
    textMuted: 'text-stone-500',
    heading: 'text-stone-500',
    input: 'border-stone-700 bg-transparent text-stone-300 placeholder:text-stone-700 focus:border-stone-500',
    btn: 'bg-stone-800 text-stone-300 hover:bg-stone-700 hover:text-stone-100',
    commentBg: 'bg-stone-900/30',
    commentBorder: 'border-stone-800',
    authed: 'text-stone-300',
    anon: 'text-stone-500 italic',
    prose: 'text-stone-400',
  };

  return (
    <section className={`mt-12 border-t ${s.border} pt-8`}>
      {/* Header — collapsible toggle */}
      <button
        onClick={toggleCollapse}
        className={`mb-6 flex w-full items-center justify-between font-mono text-sm uppercase tracking-wider ${s.heading}`}
      >
        <span>
          {total > 0 ? `${total} comment${total !== 1 ? 's' : ''}` : 'Comments'}
        </span>
        <span className={`text-xs ${s.textDim}`}>{collapsed ? '+ Show' : '- Hide'}</span>
      </button>

      {!collapsed && (
        <>
          {/* Comment form */}
          <div className={`mb-8 rounded-lg border ${s.commentBorder} ${s.bg} p-4`}>
            <div className="mb-2 flex items-center justify-between">
              <span className={`font-mono text-xs ${s.textDim}`}>
                {isAuthenticated
                  ? `Posting as ${dbUser?.display_name_custom || 'yourself'}`
                  : 'Posting anonymously'}
              </span>
              <span className={`font-mono text-xs ${body.length > 500 ? 'text-red-400' : s.textDim}`}>
                {body.length}/500
              </span>
            </div>
            <textarea
              ref={textareaRef}
              value={body}
              onChange={e => setBody(e.target.value)}
              placeholder="Say something..."
              rows={3}
              maxLength={500}
              className={`mb-3 w-full rounded border px-3 py-2 font-mono text-sm leading-relaxed focus:outline-none ${s.input}`}
            />
            {error && <p className="mb-2 font-mono text-xs text-red-400">{error}</p>}
            <button
              onClick={handleSubmit}
              disabled={posting || !body.trim() || body.length > 500}
              className={`rounded px-4 py-1.5 font-mono text-sm disabled:opacity-40 transition-colors ${s.btn}`}
            >
              {posting ? 'Posting...' : 'Post Comment'}
            </button>
          </div>

          {/* Comments list */}
          {loading && comments.length === 0 ? (
            <div className={`py-4 text-center font-mono text-sm ${s.textDim}`}>Loading...</div>
          ) : comments.length === 0 ? (
            <div className={`py-4 text-center font-mono text-sm ${s.textDim}`}>No comments yet.</div>
          ) : (
            <>
              <div className="space-y-4">
                {comments.map(c => (
                  <div
                    key={c.comment_id}
                    id={`comment-${c.comment_id}`}
                    className={`group rounded border ${s.commentBorder} ${s.commentBg} px-4 py-3 scroll-mt-24`}
                  >
                    <div className="mb-1.5 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`font-mono text-xs font-medium ${c.is_authenticated ? s.authed : s.anon}`}>
                          {c.author_name}
                        </span>
                        <a
                          href={`#comment-${c.comment_id}`}
                          className={`font-mono text-xs ${s.textDim} hover:${s.textMuted} transition-colors`}
                          title="Permalink"
                        >
                          {formatDate(c.created_at)}
                        </a>
                      </div>
                      {isAuthenticated && (
                        <button
                          onClick={async () => {
                            const token = await getIdToken();
                            if (!token) return;
                            setDupNoteId(null);
                            const res = await fetch('/api/notes', {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                              body: JSON.stringify({
                                title: `${entityId} — ${c.author_name}`,
                                body: c.body,
                                source: 'comment',
                                tickers: entityType === 'security' ? [entityId] : [],
                              }),
                            });
                            if (res.ok) {
                              setSavedNoteId(c.comment_id);
                            } else if (res.status === 409) {
                              setDupNoteId(c.comment_id);
                            }
                          }}
                          className={`rounded border px-2.5 py-1 font-mono text-xs font-bold uppercase tracking-wider transition-colors ${
                            savedNoteId === c.comment_id
                              ? 'border-ald-green/40 text-ald-green'
                              : dupNoteId === c.comment_id
                                ? 'border-ald-amber/40 text-ald-amber'
                                : `border-ald-border ${s.textDim} hover:text-ald-blue hover:border-ald-blue/40`
                          }`}
                        >
                          {savedNoteId === c.comment_id ? 'Saved' : dupNoteId === c.comment_id ? 'Already Saved' : 'Save to Notes'}
                        </button>
                      )}
                    </div>
                    <div className={`prose-comment font-mono text-sm leading-relaxed ${s.prose}`}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{c.body}</ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>

              {/* Pagination */}
              {hasMore && (
                <div className="mt-6 text-center">
                  <button
                    onClick={() => fetchComments(page + 1, true)}
                    disabled={loading}
                    className={`rounded border px-4 py-2 font-mono text-sm transition-colors disabled:opacity-40 ${s.border} ${s.textDim} hover:${s.text}`}
                  >
                    {loading ? 'Loading...' : 'Load more'}
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
