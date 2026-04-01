export default function Footer() {
  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-content">
          <div>
            <p className="footer-title">Granite Under Sandstone</p>
            <p>Jeremy Pickett &mdash; Axiomatic Fictions Series</p>
            <p>Co-developed with Claude (Anthropic). Human-directed, AI-assisted.</p>
          </div>
          <div className="footer-links">
            <a href="https://github.com/jeremy-pickett/granite" target="_blank" rel="noopener">GitHub</a>
            <span className="footer-sep">&middot;</span>
            <span>BSD 2-Clause License</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
