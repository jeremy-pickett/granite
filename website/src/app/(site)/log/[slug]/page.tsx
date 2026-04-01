'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '@/contexts/AuthContext';
import CommentsSection from '@/components/CommentsSection';

interface Post {
  post_id: number;
  slug: string;
  title: string;
  body: string;
  project: string | null;
  created_at: string;
  updated_at: string;
}

// ── Formatting toolbar ──────────────────────────────────────────────
function FormatBar({ textareaRef, value, onChange }: {
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (v: string) => void;
}) {
  function wrap(before: string, after: string) {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const selected = value.slice(start, end);
    const replacement = `${before}${selected || 'text'}${after}`;
    const newVal = value.slice(0, start) + replacement + value.slice(end);
    onChange(newVal);
    setTimeout(() => {
      ta.focus();
      ta.setSelectionRange(start + before.length, start + before.length + (selected || 'text').length);
    }, 0);
  }

  const buttons = [
    { label: 'B', title: 'Bold', action: () => wrap('**', '**') },
    { label: 'I', title: 'Italic', action: () => wrap('*', '*') },
    { label: '~', title: 'Strikethrough', action: () => wrap('~~', '~~') },
    { label: '``', title: 'Code', action: () => wrap('`', '`') },
    { label: '> ', title: 'Quote', action: () => wrap('\n> ', '\n') },
    { label: '- ', title: 'List', action: () => wrap('\n- ', '\n') },
  ];

  return (
    <div className="flex gap-1 border-b border-stone-800 pb-2 mb-2">
      {buttons.map(b => (
        <button
          key={b.title}
          type="button"
          onClick={b.action}
          title={b.title}
          className="rounded px-2 py-0.5 font-mono text-xs text-stone-500 hover:bg-stone-800 hover:text-stone-300 transition-colors"
        >
          {b.label}
        </button>
      ))}
    </div>
  );
}

// ── Share buttons ────────────────────────────────────────────────────
function ShareBar({ slug, title }: { slug: string; title: string }) {
  const [copied, setCopied] = useState(false);
  const url = typeof window !== 'undefined' ? `${window.location.origin}/log/${slug}` : '';
  const encodedUrl = encodeURIComponent(url);
  const encodedTitle = encodeURIComponent(title);

  function copyLink() {
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="mt-8 flex items-center gap-3 border-t border-stone-800 pt-6">
      <span className="font-mono text-xs text-stone-600">Share</span>
      <button onClick={copyLink} className="rounded border border-stone-700 px-2.5 py-1 font-mono text-xs text-stone-500 hover:text-stone-300 hover:border-stone-500 transition-colors">
        {copied ? 'Copied' : 'Copy Link'}
      </button>
      <a href={`https://twitter.com/intent/tweet?url=${encodedUrl}&text=${encodedTitle}`} target="_blank" rel="noopener noreferrer"
        className="rounded border border-stone-700 px-2.5 py-1 font-mono text-xs text-stone-500 hover:text-stone-300 hover:border-stone-500 transition-colors">
        X
      </a>
      <a href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`} target="_blank" rel="noopener noreferrer"
        className="rounded border border-stone-700 px-2.5 py-1 font-mono text-xs text-stone-500 hover:text-stone-300 hover:border-stone-500 transition-colors">
        LinkedIn
      </a>
      <a href={`https://news.ycombinator.com/submitlink?u=${encodedUrl}&t=${encodedTitle}`} target="_blank" rel="noopener noreferrer"
        className="rounded border border-stone-700 px-2.5 py-1 font-mono text-xs text-stone-500 hover:text-stone-300 hover:border-stone-500 transition-colors">
        HN
      </a>
      <a href={`https://www.reddit.com/submit?url=${encodedUrl}&title=${encodedTitle}`} target="_blank" rel="noopener noreferrer"
        className="rounded border border-stone-700 px-2.5 py-1 font-mono text-xs text-stone-500 hover:text-stone-300 hover:border-stone-500 transition-colors">
        Reddit
      </a>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────
export default function PostPage() {
  const params = useParams();
  const slug = params.slug as string;
  const { dbUser, getIdToken, isAuthenticated } = useAuth();
  const isAdmin = dbUser?.role === 'admin';

  const [post, setPost] = useState<Post | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editBody, setEditBody] = useState('');
  const [saving, setSaving] = useState(false);
  const editRef = useRef<HTMLTextAreaElement>(null);


  const loadPost = useCallback(async () => {
    const headers: Record<string, string> = {};
    try {
      const token = await getIdToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch {}
    const res = await fetch(`/api/posts/${slug}`, { headers });
    if (!res.ok) { setLoading(false); return; }
    const data = await res.json();
    setPost(data);
    setEditTitle(data.title);
    setEditBody(data.body);
    setLoading(false);
  }, [slug, getIdToken]);

  useEffect(() => { loadPost(); }, [loadPost]);

  async function handleSave() {
    setSaving(true);
    const token = await getIdToken();
    const res = await fetch(`/api/posts/${slug}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: editTitle, body: editBody }),
    });
    if (res.ok) {
      const updated = await res.json();
      setPost(p => p ? { ...p, title: editTitle, body: editBody, updated_at: updated.updated_at } : p);
      setEditing(false);
    }
    setSaving(false);
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', {
      weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
    });
  }

  if (loading) {
    return <main className="mx-auto max-w-3xl px-6 py-16 font-mono text-sm text-stone-600">Loading...</main>;
  }

  if (!post) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p className="font-mono text-sm text-stone-600">Post not found.</p>
        <Link href="/log" className="mt-4 inline-block font-mono text-sm text-stone-500 hover:text-stone-300">Back to .plan</Link>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      {/* Breadcrumb */}
      <div className="mb-8">
        <Link href="/log" className="font-mono text-sm text-stone-600 hover:text-stone-400 transition-colors">
          .plan
        </Link>
      </div>

      {editing ? (
        /* Edit mode */
        <div>
          <input
            type="text"
            value={editTitle}
            onChange={e => setEditTitle(e.target.value)}
            className="mb-4 w-full border-b border-stone-700 bg-transparent py-2 font-serif text-3xl font-light text-stone-100 focus:border-stone-500 focus:outline-none"
          />
          <FormatBar textareaRef={editRef} value={editBody} onChange={setEditBody} />
          <textarea
            ref={editRef}
            value={editBody}
            onChange={e => setEditBody(e.target.value)}
            rows={20}
            className="mb-4 w-full rounded border border-stone-700 bg-transparent px-3 py-2 font-mono text-sm leading-relaxed text-stone-300 focus:border-stone-500 focus:outline-none"
          />
          <div className="flex gap-3">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded bg-stone-100 px-5 py-2 font-mono text-sm font-medium text-stone-900 hover:bg-white disabled:opacity-40"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={() => { setEditing(false); setEditTitle(post.title); setEditBody(post.body); }}
              className="rounded border border-stone-700 px-5 py-2 font-mono text-sm text-stone-400 hover:text-stone-200"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        /* Read mode */
        <>
          <article>
            <div className="mb-2 flex items-center gap-3">
              <time className="font-mono text-xs text-stone-600">{formatDate(post.created_at)}</time>
              {post.project && (
                <span className="rounded bg-stone-800 px-2 py-0.5 font-mono text-xs text-stone-500">
                  {post.project}
                </span>
              )}
              {post.updated_at !== post.created_at && (
                <span className="font-mono text-xs text-stone-700">edited</span>
              )}
            </div>

            <h1 className="mb-8 font-serif text-4xl font-light leading-tight text-stone-100">
              {post.title}
            </h1>

            <div className="prose-plan font-mono text-sm leading-relaxed text-stone-400">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{post.body}</ReactMarkdown>
            </div>

            <ShareBar slug={slug} title={post.title} />

            {isAdmin && (
              <div className="mt-6 border-t border-stone-800 pt-4">
                <button
                  onClick={() => setEditing(true)}
                  className="font-mono text-xs text-stone-600 hover:text-stone-400 transition-colors"
                >
                  Edit this entry
                </button>
              </div>
            )}
          </article>

          {post && (
            <CommentsSection
              entityType="post"
              entityId={String(post.post_id)}
              variant="dark"
              prefsKey={`post-${slug}`}
            />
          )}
        </>
      )}
    </main>
  );
}
