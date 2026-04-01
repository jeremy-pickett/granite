import type { Metadata } from 'next';
import { Cormorant_Garamond, DM_Mono, Bebas_Neue } from 'next/font/google';
import '@/styles/globals.css';
import '@/styles/docs.css';
import { AuthProvider } from '@/contexts/AuthContext';

const cormorant = Cormorant_Garamond({
  subsets: ['latin'],
  weight: ['300', '400', '600'],
  style: ['normal', 'italic'],
  variable: '--font-serif',
});

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['300', '400'],
  variable: '--font-mono',
});

const bebas = Bebas_Neue({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-display',
});

export const metadata: Metadata = {
  title: 'Granite Under Sandstone',
  description: 'Compression-amplified provenance signal detection for digital media',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${cormorant.variable} ${dmMono.variable} ${bebas.variable}`}>
      <body><AuthProvider>{children}</AuthProvider></body>
    </html>
  );
}
