import '@/styles/alidade.css';
import AlidadeNav from '@/components/alidade/AlidadeNav';

export default function AlidadeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="alidade-root min-h-screen bg-ald-void text-ald-text">
      <AlidadeNav />
      {children}
    </div>
  );
}
