'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';

interface DropdownProps {
  label: string;
  items: { href: string; label: string; external?: boolean }[];
  pathname: string;
}

function Dropdown({ label, items, pathname }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const isActive = items.some(
    (item) => pathname === item.href || pathname.startsWith(item.href + '/')
  );

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="nav-dropdown" ref={ref}>
      <button
        className={`nav-dropdown-trigger${isActive ? ' active' : ''}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {label}
        <svg width="10" height="6" viewBox="0 0 10 6" fill="currentColor" style={{ marginLeft: '0.35em', opacity: 0.5 }}>
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.2" fill="none" />
        </svg>
      </button>
      {open && (
        <div className="nav-dropdown-menu">
          {items.map((item) =>
            item.external ? (
              <a
                key={item.href}
                href={item.href}
                target="_blank"
                rel="noopener"
                onClick={() => setOpen(false)}
              >
                {item.label}
              </a>
            ) : (
              <Link
                key={item.href}
                href={item.href}
                className={pathname === item.href || pathname.startsWith(item.href + '/') ? 'active' : ''}
                onClick={() => setOpen(false)}
              >
                {item.label}
              </Link>
            )
          )}
        </div>
      )}
    </div>
  );
}

const exploreItems = [
  { href: '/the-stack', label: 'The Stack' },
  { href: '/philosophy', label: 'Philosophy' },
  { href: '/future', label: 'Future' },
];

const toolsItems = [
  { href: '/inject', label: 'Inject' },
  { href: '/verify', label: 'Verify' },
];

const resourceItems = [
  { href: 'https://github.com/jeremy-pickett/granite', label: 'GitHub', external: true },
  { href: '/docs', label: 'Docs' },
  { href: '/drops', label: 'Sample Code' },
];

export default function Nav() {
  const pathname = usePathname();
  const { user, isAuthenticated, signInWithGoogle, signOut, isLoading } = useAuth();

  return (
    <nav className="nav">
      <div className="container nav-inner">
        <Link href="/home" className="nav-brand">
          Granite <span style={{ color: 'var(--text-dim)' }}>/</span> Under Sandstone
        </Link>
        <div className="nav-links">
          <Link
            href="/home"
            className={pathname === '/home' ? 'active' : ''}
          >
            Dashboard
          </Link>
          <Dropdown label="Explore" items={exploreItems} pathname={pathname} />
          <Link
            href="/log"
            className={pathname === '/log' || pathname.startsWith('/log/') ? 'active' : ''}
          >
            .plan
          </Link>
          <Link
            href="/history"
            className={pathname === '/history' || pathname.startsWith('/history/') ? 'active' : ''}
          >
            History
          </Link>
          <Dropdown label="Tools" items={toolsItems} pathname={pathname} />
          <Dropdown label="Resources" items={resourceItems} pathname={pathname} />
          <div className="nav-account">
            {isLoading ? null : isAuthenticated && user ? (
              <Link href="/alidade/profile" className="nav-user-btn" title={`Signed in as ${user.displayName || user.email}`}>
                {user.photoURL ? (
                  <img src={user.photoURL} alt="" className="nav-avatar" />
                ) : (
                  <span className="nav-avatar-fallback">
                    {user.displayName?.[0] || user.email?.[0] || '?'}
                  </span>
                )}
              </Link>
            ) : (
              <button className="nav-sign-in" onClick={signInWithGoogle}>
                Sign In
              </button>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
