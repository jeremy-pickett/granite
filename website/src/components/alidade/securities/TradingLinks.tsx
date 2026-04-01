'use client';

interface TradingLinksProps {
  ticker: string;
  securityType: string;
}

const EQUITY_BROKERS = [
  {
    name: 'Robinhood',
    url: (t: string) => `https://robinhood.com/stocks/${t}`,
    color: 'border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10',
  },
  {
    name: 'E*TRADE',
    url: (t: string) => `https://us.etrade.com/etx/sp/stockquote?symbol=${t}`,
    color: 'border-violet-500/30 text-violet-400 hover:bg-violet-500/10',
  },
  {
    name: 'Merrill',
    url: (t: string) => `https://olui2.fs.ml.com/Publish/QuoteResearch/${t}`,
    color: 'border-red-500/30 text-red-400 hover:bg-red-500/10',
  },
];

const CRYPTO_BROKERS = [
  {
    name: 'Coinbase',
    url: (t: string) => `https://www.coinbase.com/price/${t.replace(/-USD$/, '').toLowerCase()}`,
    color: 'border-blue-500/30 text-blue-400 hover:bg-blue-500/10',
  },
];

export default function TradingLinks({ ticker, securityType }: TradingLinksProps) {
  const brokers = securityType === 'crypto' ? CRYPTO_BROKERS : EQUITY_BROKERS;

  return (
    <div className="flex flex-wrap gap-2">
      {brokers.map((b) => (
        <a
          key={b.name}
          href={b.url(ticker)}
          target="_blank"
          rel="noopener noreferrer"
          className={`rounded border px-3 py-1.5 font-mono text-xs uppercase tracking-wider transition-colors ${b.color}`}
        >
          {b.name}
        </a>
      ))}
    </div>
  );
}
