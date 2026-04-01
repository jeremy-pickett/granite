import Nav from '@/components/Nav';
import Footer from '@/components/Footer';
import '@/styles/alidade.css';

export default function SiteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="granite">
      <div className="starfield" />
      <Nav />
      {children}
      <Footer />
    </div>
  );
}
