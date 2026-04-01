'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';

interface PostExcerpt {
  post_id: number;
  slug: string;
  title: string;
  project: string | null;
  published: boolean;
  excerpt: string;
  created_at: string;
}

export default function LogPage() {
  const { isAuthenticated, dbUser, getIdToken } = useAuth();
  const isAdmin = dbUser?.role === 'admin';
  const [posts, setPosts] = useState<PostExcerpt[]>([]);
  const [loading, setLoading] = useState(true);

  // New post state
  const [showEditor, setShowEditor] = useState(false);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [project, setProject] = useState('');
  const [saving, setSaving] = useState(false);

  const loadPosts = useCallback(async () => {
    const params = new URLSearchParams({ limit: '50' });
    const headers: Record<string, string> = {};
    if (isAdmin) {
      params.set('drafts', '1');
      const token = await getIdToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    fetch(`/api/posts?${params}`, { headers })
      .then(r => r.json())
      .then(data => setPosts(data.posts ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [isAdmin, getIdToken]);

  useEffect(() => { loadPosts(); }, [loadPosts]);

  async function handlePublish() {
    if (!title.trim() || !body.trim()) return;
    setSaving(true);
    const token = await getIdToken();
    const res = await fetch('/api/posts', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body, project: project || null }),
    });
    if (res.ok) {
      const post = await res.json();
      setPosts(prev => [{ ...post, published: true, excerpt: body.slice(0, 300) }, ...prev]);
      setTitle('');
      setBody('');
      setProject('');
      setShowEditor(false);
    }
    setSaving(false);
  }

  async function togglePublished(slug: string, currentlyPublished: boolean) {
    const token = await getIdToken();
    const res = await fetch(`/api/posts/${slug}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ published: !currentlyPublished }),
    });
    if (res.ok) {
      setPosts(prev => prev.map(p => p.slug === slug ? { ...p, published: !currentlyPublished } : p));
    }
  }

  async function handleDelete(slug: string) {
    if (!confirm(`Delete "${slug}"? This cannot be undone.`)) return;
    const token = await getIdToken();
    const res = await fetch(`/api/posts/${slug}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      setPosts(prev => prev.filter(p => p.slug !== slug));
    }
  }

  function formatDate(iso: string) {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <div className="mb-12 flex items-end justify-between">
        <div>
          <h1 className="font-serif text-4xl font-light tracking-tight text-stone-100">.plan</h1>
          <p className="mt-2 font-mono text-sm text-stone-500">
            Challenges, breakthroughs, and the things that took five days to figure out.
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={() => setShowEditor(!showEditor)}
            className="rounded border border-stone-700 px-4 py-2 font-mono text-sm text-stone-400 hover:border-stone-500 hover:text-stone-200 transition-colors"
          >
            {showEditor ? 'Cancel' : '+ New Entry'}
          </button>
        )}
      </div>

      {/* Editor */}
      {showEditor && (
        <div className="mb-12 rounded-lg border border-stone-700 bg-stone-900/50 p-6">
          <input
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Title"
            className="mb-3 w-full rounded border border-stone-700 bg-transparent px-3 py-2 font-serif text-xl text-stone-100 placeholder:text-stone-600 focus:border-stone-500 focus:outline-none"
          />
          <div className="mb-3 flex gap-3">
            <input
              type="text"
              value={project}
              onChange={e => setProject(e.target.value)}
              placeholder="Project tag (optional)"
              className="w-48 rounded border border-stone-700 bg-transparent px-3 py-1.5 font-mono text-sm text-stone-400 placeholder:text-stone-600 focus:border-stone-500 focus:outline-none"
            />
          </div>
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            placeholder="Write in Markdown..."
            rows={12}
            className="mb-4 w-full rounded border border-stone-700 bg-transparent px-3 py-2 font-mono text-sm leading-relaxed text-stone-300 placeholder:text-stone-600 focus:border-stone-500 focus:outline-none"
          />
          <div className="flex items-center justify-between">
            <span className="font-mono text-xs text-stone-600">{body.length} chars</span>
            <button
              onClick={handlePublish}
              disabled={saving || !title.trim() || !body.trim()}
              className="rounded bg-stone-100 px-5 py-2 font-mono text-sm font-medium text-stone-900 hover:bg-white disabled:opacity-40 transition-colors"
            >
              {saving ? 'Publishing...' : 'Publish'}
            </button>
          </div>
        </div>
      )}

      {/* Posts list */}
      {loading ? (
        <div className="py-20 text-center font-mono text-sm text-stone-600">Loading...</div>
      ) : posts.length === 0 ? (
        <div className="py-20 text-center font-mono text-sm text-stone-600">No entries yet.</div>
      ) : (
        <div className="space-y-0">
          {posts.map((p, i) => (
            <article key={p.post_id} className={`py-8 ${i > 0 ? 'border-t border-stone-800' : ''} ${!p.published ? 'opacity-50' : ''}`}>
              <div className="mb-2 flex items-center gap-3">
                <time className="font-mono text-xs text-stone-600">{formatDate(p.created_at)}</time>
                {p.project && (
                  <span className="rounded bg-stone-800 px-2 py-0.5 font-mono text-xs text-stone-500">
                    {p.project}
                  </span>
                )}
                {!p.published && (
                  <span className="rounded bg-amber-900/30 px-2 py-0.5 font-mono text-xs text-amber-500">
                    draft
                  </span>
                )}
              </div>
              <Link href={`/log/${p.slug}`} className="group">
                <h2 className="font-serif text-2xl font-light text-stone-200 group-hover:text-white transition-colors">
                  {p.title}
                </h2>
                <p className="mt-2 font-mono text-sm leading-relaxed text-stone-500">
                  {p.excerpt}{p.excerpt.length >= 300 ? '...' : ''}
                </p>
              </Link>
              {isAdmin && (
                <div className="mt-3 flex gap-4">
                  <button
                    onClick={() => togglePublished(p.slug, p.published)}
                    className="font-mono text-xs text-stone-600 hover:text-stone-400 transition-colors"
                  >
                    {p.published ? 'Unpublish' : 'Publish'}
                  </button>
                  <button
                    onClick={() => handleDelete(p.slug)}
                    className="font-mono text-xs text-stone-600 hover:text-red-400 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
