export interface Persona {
  id: number
  slug: string
  name: string
  color: string
  timeframe: string
  badge: string
  quote: string
  character: string
  signals: string[]
  alignment: number
  alignmentLabel: string
  horizon: 'days' | 'weeks' | 'months' | 'years'
  row: 1 | 2 | 'drawer'
}

export const personas: Persona[] = [
  {
    id: 1,
    slug: 'asymmetry-hunter',
    name: 'The Asymmetry Hunter',
    color: '#00358e',
    timeframe: '5\u201321 days',
    badge: 'IALD \u2191 analysts \u2193',
    quote: "You don\u2019t wait for the news. You read the room before the room knows it\u2019s being read.",
    character: "You notice that volume doesn\u2019t lie. Certain people always seem to buy at exactly the wrong time \u2014 for everyone else. You\u2019re not doing anything illegal. You\u2019re just paying attention.",
    signals: [
      'IALD/analyst divergence \u2014 the gap is the trade',
      'Options flow timing vs earnings date, 3\u201310 days pre',
      'Congressional co-occurrence \u00b13 days of exec transaction',
      'Pre-announcement volume delta: day -1, 0, +1 vs 30-day mean',
    ],
    alignment: 12,
    alignmentLabel: 'Deliberately inverted \u2014 high IALD, neutral analyst = maximum signal.',
    horizon: 'days',
    row: 1,
  },
  {
    id: 2,
    slug: 'board-whisperer',
    name: 'The Board Whisperer',
    color: '#c8102e',
    timeframe: '30\u201390 days',
    badge: 'Form 4 cluster',
    quote: "Executives lie in press releases. They tell the truth with their brokerage accounts.",
    character: "A CEO who sells on a 10b5-1 plan is noise. A CFO who buys discretionarily three weeks before a quiet period is a signal. You want to know everything about everyone in that boardroom.",
    signals: [
      'Discretionary buy vs programmatic 10b5-1 \u2014 categorically different',
      'Cluster buys: 2+ insiders in same 10-day window',
      'Board interlocks \u2014 cross-reference concurrent board seats',
      '10b5-1 modification within 6 months of material announcement',
    ],
    alignment: 52,
    alignmentLabel: 'Partially aligned \u2014 insider accumulation should eventually move analyst consensus.',
    horizon: 'weeks',
    row: 1,
  },
  {
    id: 3,
    slug: 'volatility-archaeologist',
    name: 'The Volatility Archaeologist',
    color: '#555555',
    timeframe: '2\u201314 days',
    badge: 'Vol anomaly',
    quote: "Beneath every unexplained price spike is a story that hasn\u2019t been told yet.",
    character: "You\u2019ve learned to recognize the shape of a secret \u2014 the volume that precedes nothing, the options that expire perfectly, the quiet that follows a big move. You\u2019re building a fossil record.",
    signals: [
      'Unexplained volume anomaly ledger \u2014 date-stamped, awaiting catalyst',
      'Prediction market divergence from equity behavior',
      'Intraday vol profiling around world events',
      'Post-anomaly suppression pattern detection',
    ],
    alignment: 5,
    alignmentLabel: 'Analysts are irrelevant here. IALD anomaly ledger is the only signal.',
    horizon: 'days',
    row: 1,
  },
  {
    id: 4,
    slug: 'analyst-fader',
    name: 'The Analyst Fader',
    color: '#f5c800',
    timeframe: '10\u201330 days',
    badge: 'Earnings cycle',
    quote: "The upgrade comes after the run. The price target raise arrives at the top.",
    character: "You\u2019ve read enough analyst reports to know they\u2019re mostly eulogies written before the funeral. When IALD says one thing and the Street says another, you know which one is looking at real data.",
    signals: [
      'Pre-earnings price run \u2014 days -10 to -1 vs 30-day baseline',
      'Analyst revision timing lag vs IALD signal',
      'Insider selling into analyst upgrades \u2014 short signal',
      'Consensus clustering: 4+ upgrades in 2 weeks = likely top',
    ],
    alignment: 5,
    alignmentLabel: 'Inverted \u2014 maximum IALD/analyst divergence is the entry signal.',
    horizon: 'weeks',
    row: 2,
  },
  {
    id: 5,
    slug: 'governance-arbitrageur',
    name: 'The Governance Arbitrageur',
    color: '#c8102e',
    timeframe: '30\u2013180 days',
    badge: 'Regulatory lag',
    quote: "Power leaves fingerprints. You\u2019ve learned to read them.",
    character: "The senator who buys the defense contractor the week before the contract announcement. The regulator who joins the board six months after approving the merger. You operate in the space between what\u2019s legal and what\u2019s disclosed.",
    signals: [
      'Revolving door tracker \u2014 regulatory officials to board seats',
      'Congressional \u00b13-day co-occurrence \u2014 highest conviction signal',
      'Reported gift disclosures from vendors and regulated parties',
      'Regulatory decision timeline vs equity position changes',
    ],
    alignment: 10,
    alignmentLabel: 'Analysts almost never cover governance risk until it becomes headline risk.',
    horizon: 'months',
    row: 2,
  },
  {
    id: 6,
    slug: 'diligent-saver',
    name: 'The Diligent Saver',
    color: '#00358e',
    timeframe: '90d \u2013 2yr',
    badge: 'IALD + analysts \u2713',
    quote: "You want to beat the index by enough to matter and sleep at night.",
    character: "You\u2019ve watched people try to get rich quickly. You want to beat the index by enough to matter, sleep at night, and not spend your weekends watching tickers. Divergence is a disqualifier, not an opportunity.",
    signals: [
      'Full IALD/analyst alignment \u2014 both must agree directionally',
      'Historic alpha vs benchmark \u2014 boring outperformance preferred',
      'Low anomaly history, clean governance record required',
      'Steady institutional accumulation as quality filter',
    ],
    alignment: 95,
    alignmentLabel: 'Maximum alignment required \u2014 both must agree. Divergence is a disqualifier.',
    horizon: 'years',
    row: 2,
  },
  {
    id: 7,
    slug: 'catalyst-calendar',
    name: 'The Catalyst Calendar',
    color: '#f5c800',
    timeframe: '5\u201315 days',
    badge: 'Event-anchored',
    quote: "You don\u2019t guess. You navigate. Every quarter has a shape.",
    character: "You use IALD not to predict the catalyst, but to determine which way the smart money is leaning into it. A known event with an unknown outcome plus a directional signal is the cleanest trade there is.",
    signals: [
      'Event calendar \u2014 earnings, Fed, FDA PDUFA dates',
      'Prediction markets: Kalshi, Polymarket odds on related outcomes',
      'Pre-event volume delta \u2014 day -10 to day -1',
      'Post-event resolution scoring',
      'Congressional \u00b13-day co-occurrence',
    ],
    alignment: 65,
    alignmentLabel: 'Directional agreement amplifies conviction. Disagreement is itself a signal.',
    horizon: 'days',
    row: 'drawer',
  },
]
