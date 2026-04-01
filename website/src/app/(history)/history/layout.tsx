import '@/styles/history.css';

export default function HistoryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="history-world">
      {children}
    </div>
  );
}
