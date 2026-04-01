'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function LockerRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace('/alidade/profile'); }, [router]);
  return null;
}
