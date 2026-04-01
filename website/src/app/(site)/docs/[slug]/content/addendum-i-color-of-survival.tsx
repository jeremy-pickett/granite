export default function AddendumIColorOfSurvivalContent() {
  return (
    <>
<header className="page-hero">
  <div className="container">
    <p className="hero-series">Addendum I</p>
    <h1>The Color of Survival</h1>
    <p className="hero-subtitle">Granite Under Sandstone &mdash; Addendum Series</p>
  </div>
</header>

<section className="section">
  <div className="container content-narrow">
    <h2>I.1 The Question</h2>
    <p>Every RGB pixel has three values. Every pair of values produces a distance. There are three pairs: |R−G|, |R−B|, |G−B|. The scheme has used |R−G| since its first implementation. This was an arbitrary choice. The question is whether it was the right one.</p>
    <p>It was not.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>I.2 The YCbCr Coupling</h2>
    <p>JPEG does not compress RGB. It converts to YCbCr first:</p>
    <p>Y  =  0.299 R  +  0.587 G  +  0.114 B</p>
    <p>Cb = -0.169 R  -  0.331 G  +  0.500 B</p>
    <p>Cr =  0.500 R  -  0.419 G  -  0.081 B</p>
    <p>Green dominates luminance (0.587). Red contributes moderately (0.299). Blue contributes almost nothing (0.114). The luminance channel (Y) receives gentle quantization. The chrominance channels (Cb, Cr) receive aggressive quantization.</p>
    <p>This conversion couples all three RGB channels. A perturbation in any one RGB channel pair creates signal in all three pairs after the YCbCr round-trip, because changing R or G or B changes Y and Cb and Cr simultaneously, and quantization error in YCbCr redistributes across all RGB channels on decode.</p>
    <p><strong>Consequence: </strong>The three RGB channel pairs are NOT independent information channels through JPEG. A perturbation embedded in |R−G| creates detectable signal in |R−B| and |G−B| as well. Three correlated views of one perturbation, not three independent perturbations.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>I.3 The Empirical Finding</h2>
    <h3>I.3.1 Cross-Pair Leakage</h3>
    <p>Twin markers embedded in |R−G| only (250 markers, 1024×1024, JPEG Q95):</p>
    <div className="table-wrap"><table>
<thead><tr><th>Channel Pair</th><th>Rate Ratio</th><th>p-value</th><th>Signal?</th></tr></thead>
<tbody>
<tr><td>R-G (embedded)</td><td>3.42×</td><td>1.0 × 10⁻²³</td><td>YES</td></tr>
<tr><td>R-B (not embedded)</td><td>2.08×</td><td>3.7 × 10⁻⁷</td><td>YES (leaked)</td></tr>
<tr><td>G-B (not embedded)</td><td>3.71×</td><td>1.3 × 10⁻²⁴</td><td>YES (leaked)</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table I1. </strong><em>Cross-pair leakage. Embedding in R-G creates detectable signal in all three pairs. G-B leaked signal is actually STRONGER than the directly embedded R-G signal. The YCbCr coupling distributes the perturbation across all pairs.</em></p>
    <p><strong>Notable: </strong>The leaked G-B signal (3.71×) is stronger than the directly embedded R-G signal (3.42×). This is not an error. The perturbation energy that flowed into chrominance through the color space conversion is more detectable in G-B because blue’s low contribution to Y (0.114) means the G-B perturbation is less attenuated by luminance quantization.</p>
    <h3>I.3.2 Interference Test</h3>
    <p>Embedding R-B on top of existing R-G embedding:</p>
    <p><strong>R-G ratio before R-B embedding: </strong>3.65×, p = 2.8 × 10⁻²⁷</p>
    <p><strong>R-G ratio after R-B embedding: </strong>3.40×, p = 3.0 × 10⁻²³</p>
    <p><strong>Degradation: </strong>6.7%. The pairs coexist with minimal destructive interference.</p>
    <h3>I.3.3 Cascade Survival by Channel Pair</h3>
    <p>All three pairs embedded, JPEG compression cascade:</p>
    <div className="table-wrap"><table>
<thead><tr><th>Quality</th><th>R-G ratio</th><th>R-G p</th><th>R-B ratio</th><th>R-B p</th><th>G-B ratio</th><th>G-B p</th></tr></thead>
<tbody>
<tr><td>Q95</td><td>3.41</td><td>2.4×10⁻²³</td><td>2.25</td><td>8.5×10⁻⁹</td><td>2.41</td><td>5.8×10⁻⁹</td></tr>
<tr><td>Q85</td><td>2.61</td><td>1.1×10⁻¹²</td><td>2.26</td><td>5.0×10⁻⁹</td><td>3.91</td><td>1.4×10⁻²⁸</td></tr>
<tr><td>Q75</td><td>2.77</td><td>1.4×10⁻¹⁴</td><td>2.19</td><td>4.5×10⁻⁸</td><td>3.60</td><td>4.2×10⁻²⁴</td></tr>
<tr><td>Q60</td><td>2.34</td><td>2.1×10⁻⁹</td><td>1.68</td><td>7.2×10⁻⁴</td><td>2.53</td><td>2.2×10⁻¹⁰</td></tr>
<tr><td>Q40</td><td>1.43</td><td>2.4×10⁻²</td><td>0.95</td><td>6.4×10⁻¹</td><td>1.64</td><td>2.7×10⁻³</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table I2. </strong><em>Cascade survival by channel pair. G-B is empirically superior to R-G at every quality level below Q95. R-B dies at Q40. G-B shows amplification at Q85 (ratio 3.91, higher than Q95). This is the granite effect in the chrominance domain.</em></p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>I.4 Why G-B Wins</h2>
    <p>The explanation follows directly from the YCbCr conversion weights.</p>
    <p><strong>|R−G| perturbation: </strong>Moves the two channels with the highest luminance contribution (R=0.299, G=0.587). Large Y shift. Luminance quantizer sees it. Luminance quantizer is gentle, but it’s still fighting the perturbation. Moderate survival.</p>
    <p><strong>|R−B| perturbation: </strong>Moves R (Y=0.299, Cr=0.500) and B (Y=0.114, Cb=0.500). The perturbation splits across luminance and chrominance with no dominant home. Both quantizers attack it. Neither preserves it. Worst survival.</p>
    <p><strong>|G−B| perturbation: </strong>Moves G (Y=0.587) and B (Y=0.114). The net luminance change is dominated by G, but the difference |G−B| maps primarily to chrominance, specifically to Cb which weights B at 0.500 and G at −0.331. The perturbation energy concentrates in the chrominance domain. Chrominance quantization is more aggressive, which means each compression pass penalizes the perturbation harder, which means the variance anomaly diverges faster from the smooth background. More aggressive quantization drives faster amplification.</p>
    <p>The G-B amplification at Q85 (ratio jumping from 2.41 to 3.91) is the granite effect operating in chrominance. The same mechanism, stronger, because the quantization is harsher. The harsher the quantization, the faster the amplification. The chrominance domain is the harshest quantization environment in the codec. G-B thrives there.</p>
    <p className="lead"><em>The optimal channel pair is G-B, not R-G. The default in all existing code should be changed. This is not a marginal improvement. At Q85, G-B outperforms R-G by 50% (3.91 vs 2.61). At Q40, G-B is the only pair still detectable. The R-G default was arbitrary. The G-B recommendation is empirical.</em></p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>I.5 The Diagnostic Architecture</h2>
    <p>Although the three channel pairs are not independent information channels (YCbCr coupling prevents independence), they have differentiated survival profiles. The <em>pattern of which pairs survive a given transform</em> is diagnostic of the transform class.</p>
    <h3>I.5.1 Channel Pair as Transform Classifier</h3>
    <div className="table-wrap"><table>
<thead><tr><th>Transform</th><th>R-G</th><th>R-B</th><th>G-B</th><th>Diagnosis</th></tr></thead>
<tbody>
<tr><td>Light compression (Q85+)</td><td>Alive</td><td>Alive</td><td>Strongest</td><td>Benign pipeline</td></tr>
<tr><td>Heavy compression (Q40)</td><td>Marginal</td><td>Dead</td><td>Alive</td><td>Aggressive pipeline</td></tr>
<tr><td>Grayscale conversion</td><td>Dead</td><td>Dead</td><td>Dead</td><td>Color destroyed</td></tr>
<tr><td>Color balance shift</td><td>Shifted</td><td>Shifted</td><td>Shifted</td><td>Selective color manip.</td></tr>
<tr><td>Chroma subsample change</td><td>Moderate</td><td>Damaged</td><td>Damaged</td><td>Chroma pipeline change</td></tr>
<tr><td>Targeted G-B suppression</td><td>Alive</td><td>Alive</td><td>Dead</td><td>State D. Deliberate.</td></tr>
</tbody></table></div>
    <p className="lead"><strong>Table I3. </strong><em>Predicted channel pair survival by transform class. The pattern of alive/dead/damaged across three pairs classifies the transformation. Rows marked “predicted” are derived from the YCbCr conversion weights and codec architecture but have not been empirically tested.</em></p>
    <h3>I.5.2 Integration with Spatial Scale Channels</h3>
    <p>The channel pair diagnostic is orthogonal to the spatial scale diagnostic from the main scheme. Spatial scales (pixel, subblock, DC) classify the <em>severity</em> of the transform. Channel pairs classify the <em>type</em> of the transform. Together they form a two-dimensional diagnostic matrix.</p>
    <p>Three spatial scales × three channel pairs = nine cells in the diagnostic matrix. Each cell has a binary alive/dead state after a given transform. The pattern across all nine cells is a transformation fingerprint with 2⁹ = 512 possible states. Each state corresponds to a specific combination of transform severity and transform type.</p>
    <p>The pixel scale dies under heavy compression but survives resize. The subblock scale survives heavy compression but may not survive aggressive resize. The DC scale survives everything except deliberate DC manipulation. Within each scale, G-B survives longest, R-G survives moderate compression, R-B dies first.</p>
    <p>The nine-cell matrix is not nine independent channels. It is three correlated channel pairs observed at three partially independent spatial scales. The effective diagnostic resolution is somewhere between 2³ = 8 states (if channel pairs add no information beyond spatial scales) and 2⁹ = 512 states (if all cells are independent). The empirical resolution requires testing, which has not been performed.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>I.6 The Multi-Scale Defense</h2>
    <p>Every attack that kills one cell of the diagnostic matrix reveals which cell was killed. The identity of the dead cell classifies the attack.</p>
    <p>An adversary who knows the scheme and specifically targets G-B at pixel scale (the strongest single channel) must apply per-position smoothing of the blue and green channels at marker positions. This suppresses the G-B pixel-scale cell. But the leaked signal in R-G and R-B at pixel scale survives because the adversary targeted G-B specifically. And the G-B signal at subblock and DC scales survives because the adversary targeted pixel-scale specifically.</p>
    <p>To suppress all nine cells, the adversary must: smooth all three channel pair relationships at all three spatial scales at every marker position. That is: per-pixel smoothing of R, G, and B channels; subblock-average equalization across quadrants; and DC-level average shifting across blocks. Three independent spatial operations, each affecting all three color channels, at every marker position in the image.</p>
    <p>The cost scales with markers × scales × pairs. The forensic residue scales identically. The legal exposure scales identically. The adversary’s optimal move, as always, is to avoid marked content entirely.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>I.7 The Generalized Principle</h2>
    <p>The channel pair analysis reveals an instance of a broader principle:</p>
    <p className="lead"><em>Any system that partitions data into chunks for processing creates a boundary condition. The boundary enforces independence. The interior enforces correlation. Any perturbation embedded in the correlated interior is amplified by the processing that exploits that correlation, because the processing is optimized for the natural statistics of the interior and the perturbation violates those statistics.</em></p>
    <p>JPEG partitions spatially (8×8 blocks) and spectrally (YCbCr conversion). The spatial partition creates correlated block interiors. The spectral partition creates coupled color channels. The perturbation is amplified by spatial quantization (the granite effect in the block interior) and differentiated by spectral quantization (different channel pairs have different survival profiles because the codec’s color space conversion weights them differently).</p>
    <p>The spatial partition gives us detection. The spectral partition gives us diagnosis. Both are consequences of the same architectural principle: the codec’s optimization structure creates exploitable channels in every dimension it partitions.</p>
    <p>This principle is not specific to JPEG. Any lossy codec that partitions data spatially (blocks, windows, frames) AND spectrally (color space conversion, psychoacoustic model, frequency decomposition) creates the same two-dimensional diagnostic opportunity. The specific survival profiles differ per codec. The architectural principle is universal.</p>
    </div></section>
<section className="section section-alt"><div className="container content-narrow">
    <h2>I.8 Recommendations</h2>
    <p><strong>Change the default channel pair from R-G to G-B.</strong> The existing codebase uses |R−G| as DEFAULT_CHANNEL_PAIRS. This should be changed to |G−B| = (1, 2). G-B is empirically superior at every quality level below Q95, shows stronger amplification, and is the last pair standing at Q40. This is a one-line code change with significant survival improvement.</p>
    <p><strong>Measure all three pairs for detection.</strong> Embed in G-B as the primary channel. Measure R-G and R-B as diagnostic echoes. The cost is two additional distance measurements per position, which is trivial. The benefit is transform classification from the channel pair survival pattern.</p>
    <p><strong>Do not attempt to embed independently in all three pairs.</strong> The YCbCr coupling prevents independence. Embedding in multiple pairs does not multiply capacity. It modestly increases detection strength (multiple views of the same perturbation) at the cost of larger pixel-domain changes. The single-pair G-B embedding with three-pair detection is the optimal strategy.</p>
    <p><strong>Incorporate channel pair survival into the four-state model.</strong> State C (degraded signal from benign transforms) can be subclassified by which channel pairs survived and which didn’t. State D (interference) can be subclassified by which pairs were targeted. The diagnostic resolution of the state model increases without additional embedding cost.</p>
    </div></section>
<section className="section"><div className="container content-narrow">
    <h2>I.9 What This Changes</h2>
    <p>The scheme’s operating capability at heavy compression improves significantly. The Q40 detection threshold, previously marginal on R-G (ratio 1.43, p = 0.024), becomes statistically significant on G-B (ratio 1.64, p = 0.003). The operating envelope at the aggressive-compression end extends deeper into messaging app territory (WhatsApp Q70, Instagram recompression) where survival matters most.</p>
    <p>The diagnostic architecture gains a new axis. Spatial scale tells you how severe the transform was. Channel pair tells you what type of transform was applied. The two axes are orthogonal because they exploit different partitioning dimensions of the codec’s architecture (spatial blocks vs. color space conversion). Together they provide a richer transformation fingerprint than either axis alone.</p>
    <p>And the finding was hiding in the code since day one. DEFAULT_CHANNEL_PAIRS was always a parameterized constant. The framework always accepted channel pair as an argument. The R-G default was chosen without testing alternatives. The G-B superiority was discovered by asking the simplest possible question: is one channel pair better than the others?</p>
    <p className="lead"><em>The answer was in the code. The question had not been asked. The code was ready. The assumption was not examined. That is how axiomatic fictions work. Not by hiding the answer. By discouraging the question.</em></p>
    <p className="lead"><em>Empirical results from one synthetic image at 1024×1024. Pending validation on real photographs.</em></p>
    <p className="lead"><em>Channel pair predictions in Table I3 are derived from YCbCr weights, not measured. Each prediction is independently testable.</em></p>
    <p className="lead"><strong><em>The G-B finding changes the default. The diagnostic architecture extends the scheme. Both were found by asking “what did we assume?”</em></strong></p>
    <p>Jeremy Pickett — March 19, 2026</p>
  </div>
</section>
    </>
  );
}
