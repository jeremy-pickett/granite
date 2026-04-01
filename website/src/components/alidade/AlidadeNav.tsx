'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useState, useEffect, useCallback, useRef } from 'react';

export default function AlidadeNav() {
  const pathname = usePathname();
  const { user, isAuthenticated, getIdToken } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [exploreOpen, setExploreOpen] = useState(false);
  const exploreRef = useRef<HTMLDivElement>(null);

  const fetchUnread = useCallback(async () => {
    try {
      const token = await getIdToken();
      if (!token) return;
      const res = await fetch('/api/alerts/unread', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUnreadCount(data.count);
      }
    } catch {}
  }, [getIdToken]);

  useEffect(() => {
    if (!isAuthenticated) return;
    fetchUnread();
    const interval = setInterval(fetchUnread, 60000);
    return () => clearInterval(interval);
  }, [isAuthenticated, fetchUnread]);

  // Clear badge when user navigates to alerts
  useEffect(() => {
    if (pathname === '/alidade/alerts') {
      setUnreadCount(0);
    }
  }, [pathname]);

  // Close Explore dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (exploreRef.current && !exploreRef.current.contains(e.target as Node)) {
        setExploreOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const linkClass = (href: string) =>
    `font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
      pathname === href || pathname.startsWith(href + '/')
        ? 'text-ald-text'
        : 'text-ald-text-dim hover:text-ald-text'
    }`;

  const exploreActive = pathname === '/alidade/alerts' || pathname.startsWith('/alidade/alerts/')
    || pathname === '/alidade/watchlist' || pathname.startsWith('/alidade/watchlist/')
    || pathname === '/alidade/simulator' || pathname.startsWith('/alidade/simulator/')
    || pathname === '/alidade/suggestions' || pathname.startsWith('/alidade/suggestions/')
    || pathname === '/alidade/cohorts' || pathname.startsWith('/alidade/cohorts/')
    || pathname === '/alidade/notes' || pathname.startsWith('/alidade/notes/');

  return (
    <nav className="sticky top-0 z-50 border-b border-ald-border bg-ald-void/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
        <Link
          href="/alidade"
          className="font-mono text-sm font-light uppercase tracking-[0.15em] text-ald-blue hover:text-ald-ivory transition-colors"
        >
          Alidade
        </Link>
        <div className="flex items-center gap-6">
          {/* 1. Dashboard */}
          <Link href="/alidade/dashboard" className={linkClass('/alidade/dashboard')}>
            Dashboard
          </Link>

          {/* 2. Explore dropdown → Alerts, Watchlist */}
          <div className="relative" ref={exploreRef}>
            <button
              onClick={() => setExploreOpen(!exploreOpen)}
              className={`font-mono text-sm uppercase tracking-[0.1em] transition-colors flex items-center gap-1 ${
                exploreActive ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
              }`}
            >
              Explore
              <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{ opacity: 0.5 }}>
                <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.2" />
              </svg>
            </button>
            {exploreOpen && (
              <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 min-w-[180px] rounded border border-ald-border bg-ald-void/95 backdrop-blur-md py-1 shadow-lg z-50">
                <Link
                  href="/alidade/alerts"
                  onClick={() => setExploreOpen(false)}
                  className={`relative flex items-center gap-2.5 px-4 py-2 font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                    pathname === '/alidade/alerts' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <path d="M7 1L3 5v3l-1.5 1.5V11h11V9.5L11 8V5L7 1z" stroke="#C53030" strokeWidth="1.2" fill="#C53030" fillOpacity="0.15"/>
                    <circle cx="7" cy="12.5" r="1" fill="#C53030"/>
                  </svg>
                  Alerts
                  {unreadCount > 0 && (
                    <span className="absolute right-3 top-1/2 -translate-y-1/2 flex h-4 min-w-4 items-center justify-center rounded-full bg-ald-red px-1 font-mono text-[10px] font-bold text-white">
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  )}
                </Link>
                <Link
                  href="/alidade/watchlist"
                  onClick={() => setExploreOpen(false)}
                  className={`flex items-center gap-2.5 px-4 py-2 font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                    pathname === '/alidade/watchlist' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <circle cx="7" cy="7" r="5.5" stroke="#2956A8" strokeWidth="1.2"/>
                    <circle cx="7" cy="7" r="2" fill="#2956A8"/>
                    <path d="M7 1.5V3M7 11v1.5M1.5 7H3M11 7h1.5" stroke="#B7791F" strokeWidth="1" strokeLinecap="round"/>
                  </svg>
                  Watchlist
                </Link>
                <Link
                  href="/alidade/simulator"
                  onClick={() => setExploreOpen(false)}
                  className={`flex items-center gap-2.5 px-4 py-2 font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                    pathname === '/alidade/simulator' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <rect x="1" y="1" width="12" height="12" rx="2" stroke="#2956A8" strokeWidth="1.2"/>
                    <polyline points="3,10 5,6 7,8 9,4 11,5" stroke="#1A7D42" strokeWidth="1.2" fill="none" strokeLinejoin="round"/>
                    <circle cx="9" cy="4" r="1.5" fill="#B7791F"/>
                  </svg>
                  Simulator
                </Link>
                <Link
                  href="/alidade/suggestions"
                  onClick={() => setExploreOpen(false)}
                  className={`flex items-center gap-2.5 px-4 py-2 font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                    pathname === '/alidade/suggestions' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <rect x="1" y="1" width="5" height="5" fill="#C53030" fillOpacity="0.8" rx="1"/>
                    <rect x="8" y="1" width="5" height="5" fill="#2956A8" fillOpacity="0.8" rx="1"/>
                    <rect x="4.5" y="8" width="5" height="5" fill="#B7791F" fillOpacity="0.8" rx="1"/>
                    <circle cx="7" cy="7" r="1.5" fill="#1F2937"/>
                  </svg>
                  IALD Suggestions
                </Link>
                <Link
                  href="/alidade/cohorts"
                  onClick={() => setExploreOpen(false)}
                  className={`flex items-center gap-2.5 px-4 py-2 font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                    pathname === '/alidade/cohorts' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <circle cx="5" cy="5" r="3" stroke="#0E7FAD" strokeWidth="1.2" fill="#0E7FAD" fillOpacity="0.12"/>
                    <circle cx="9" cy="5" r="3" stroke="#2956A8" strokeWidth="1.2" fill="#2956A8" fillOpacity="0.12"/>
                    <circle cx="7" cy="9" r="3" stroke="#1A7D42" strokeWidth="1.2" fill="#1A7D42" fillOpacity="0.12"/>
                  </svg>
                  Cohorts
                </Link>
                <Link
                  href="/alidade/notes"
                  onClick={() => setExploreOpen(false)}
                  className={`flex items-center gap-2.5 px-4 py-2 font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                    pathname === '/alidade/notes' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
                  }`}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
                    <rect x="2" y="1" width="10" height="12" rx="1.5" stroke="#4B5563" strokeWidth="1.2"/>
                    <line x1="4.5" y1="4" x2="9.5" y2="4" stroke="#B7791F" strokeWidth="1" strokeLinecap="round"/>
                    <line x1="4.5" y1="6.5" x2="9.5" y2="6.5" stroke="#B7791F" strokeWidth="1" strokeLinecap="round"/>
                    <line x1="4.5" y1="9" x2="7.5" y2="9" stroke="#B7791F" strokeWidth="1" strokeLinecap="round"/>
                  </svg>
                  My Notes
                </Link>
              </div>
            )}
          </div>

          {/* 3. .plan */}
          <Link href="/log" className={linkClass('/log')}>
            .plan
          </Link>

          {/* 4. Projects */}
          <Link
            href="/"
            className="font-mono text-sm uppercase tracking-[0.1em] text-ald-text-dim hover:text-ald-text transition-colors"
          >
            Projects
          </Link>

          {/* Profile — right-aligned, next to avatar */}
          {isAuthenticated && user ? (
            <Link href="/alidade/profile" className="flex items-center gap-2">
              <span className={`font-mono text-sm uppercase tracking-[0.1em] transition-colors ${
                pathname === '/alidade/profile' ? 'text-ald-text' : 'text-ald-text-dim hover:text-ald-text'
              }`}>
                Profile
              </span>
              {user.photoURL ? (
                <img
                  src={user.photoURL}
                  alt=""
                  className="h-9 w-9 rounded-full border border-ald-border hover:border-ald-blue transition-colors"
                />
              ) : (
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-ald-blue/20 font-mono text-sm text-ald-blue hover:bg-ald-blue/30 transition-colors">
                  {user.displayName?.[0] || '?'}
                </span>
              )}
            </Link>
          ) : (
            <Link
              href="/alidade/login"
              className="rounded border border-ald-blue/30 px-3 py-1 font-mono text-sm uppercase tracking-wider text-ald-blue hover:bg-ald-blue hover:text-ald-void transition-colors"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
