'use client';

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from 'firebase/auth';
import { auth, googleProvider } from '@/lib/firebase';

interface AuthContextType {
  user: User | null;
  dbUser: DbUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  getIdToken: () => Promise<string | null>;
}

interface DbUser {
  user_id: number;
  role: string;
  subscription_tier: string;
  display_name_custom?: string;
}

const AuthContext = createContext<AuthContextType | null>(null);

async function syncUser(firebaseUser: User): Promise<DbUser | null> {
  try {
    const token = await firebaseUser.getIdToken();
    const res = await fetch('/api/auth/sync', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      return await res.json();
    }
  } catch (e) {
    console.error('User sync failed:', e);
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [dbUser, setDbUser] = useState<DbUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let initialLoad = true;
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        const synced = await syncUser(firebaseUser);
        setDbUser(synced);
        setIsLoading(false);
        initialLoad = false;
      } else {
        setDbUser(null);
        // On the very first callback, Firebase may fire null before restoring
        // a persisted session. Use a short delay to avoid premature redirects.
        if (initialLoad) {
          initialLoad = false;
          await new Promise(r => setTimeout(r, 500));
        }
        setIsLoading(false);
      }
    });
    return unsubscribe;
  }, []);

  const signInWithGoogle = async () => {
    const result = await signInWithPopup(auth, googleProvider);
    const synced = await syncUser(result.user);
    setDbUser(synced);
  };

  const signOut = async () => {
    await firebaseSignOut(auth);
    setDbUser(null);
  };

  const getIdToken = useCallback(async () => {
    if (!user) return null;
    return user.getIdToken();
  }, [user]);

  return (
    <AuthContext.Provider
      value={{
        user,
        dbUser,
        isLoading,
        isAuthenticated: !!user,
        signInWithGoogle,
        signOut,
        getIdToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
