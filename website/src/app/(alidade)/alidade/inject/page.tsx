'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function InjectRedirect() {
  const router = useRouter();
  useEffect(() => { router.replace('/inject'); }, [router]);
  return null;
}
