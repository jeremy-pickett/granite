import Link from 'next/link';

export default function LayerGContent() {
  return (
    <>
      <header className="page-hero">
        <div className="container">
          <p className="hero-series">Layer G Specification</p>
          <h1>Halo</h1>
          <p className="hero-subtitle">Rotation-resilient sentinel detection. The field outlives the mass.</p>
        </div>
      </header>

      <section className="section">
        <div className="container content-narrow">
          <h2>Purpose and Role in the Stack</h2>
          <blockquote>
            <p>&ldquo;The adversary who removes the sentinel leaves the field intact. The field still points at what was there.&rdquo;</p>
          </blockquote>
          <p>Layers E and F encode payload information in the positional relationships between sentinels. Rotate the image by 30 degrees and that relationship changes. The sentinel is detectable in isolation, but the positional grammar that encodes the payload has been disrupted.</p>
          <p>More critically: an adversary who applies a rotation and then removes the sentinel has eliminated all positional evidence. No structure remains that points back at where the sentinel was. This is the gap Layer G fills.</p>

          <h3>The Gravitational Lensing Analogy</h3>
          <p>The analogy is precise, not decorative. A gravitational lens does not destroy what lies behind it. It distorts the surrounding space in a radially symmetric, predictable way. Observers who detect the distortion pattern can infer the existence, position, and properties of the lensing mass even without directly observing it. The distortions are force arrows. They all point at something.</p>
          <p>Layer G embeds exactly this structure: a radial field of perturbed pixels surrounding each sentinel. Each pixel in the field is a force arrow pointing toward the center. The center is detectable not by finding the sentinel directly, but by finding the convergence point of all surrounding force arrows. And when the sentinel is removed, the force arrows remain. <strong>The field outlives the mass. The void is detectable.</strong></p>
          <p>Layer G sits at position 6 in the dependency chain. It consumes sentinel center positions from Layer F and wraps them with a radial lensing field. Its output &mdash; halo positions and states &mdash; feeds no downstream layer but can inform forensic re-analysis after Layer H recovers original image coordinates.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>What This Layer Detects and Proves</h2>
          <div className="grid-3" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark">
              <h3>Detects</h3>
              <p>Sentinel presence at any rotation angle (0&deg; through 360&deg;).</p>
              <p>Sentinel removal after embedding: VOID state where inner disk is absent but outer ring persists.</p>
              <p>Halo center positions in rotated images, enabling Layer F payload reconstruction after rotation correction.</p>
              <p>Force-arrow convergence: the radial structure that identifies the center even without the sentinel.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--pass)' }}>
              <h3 style={{ color: 'var(--pass)' }}>Proves</h3>
              <p><strong>Participation:</strong> the image was processed by a tool implementing this protocol.</p>
              <p><strong>Rotation resilience:</strong> 100% detection at all tested angles (0&deg;, 15&deg;, 30&deg;, 45&deg;, 90&deg;, 180&deg;) on DIV2K corpus.</p>
              <p><strong>VOID state:</strong> inner disk absent, outer ring elevated &mdash; may support an inference of targeted inner-disk removal.</p>
              <p><strong>State D&#x2082; (force-arrow):</strong> the halo field survives sentinel removal; the adversary who removes the sentinel cannot erase the surrounding field without additional targeted intervention.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--tamper)' }}>
              <h3 style={{ color: 'var(--tamper)' }}>Does Not Prove</h3>
              <p>Crop or stitch geometry (Layer H handles this).</p>
              <p>Payload content (Layer F handles this; Layer G provides halo centers for rotation-corrected payload recovery).</p>
              <p>Identity of the entity that performed any removal.</p>
              <p><em>These inferences require the broader evidentiary context described in the <Link href="/the-stack" style={{ color: 'var(--amber)' }}>System Model</Link>.</em></p>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>Explicit Constraints</h2>
          <p><em>Each item is covered by a peer layer or documented as an open item.</em></p>

          <div className="param-block" style={{ marginTop: '1.5rem' }}>
            <dl>
              <dt>Does not encode payload</dt>
              <dd>Layer G is a detection and attribution layer. Information encoding is Layer F&rsquo;s domain. Layer G provides halo centers; Layer F uses them to locate sentinels; the sentinel positions carry the payload.</dd>

              <dt>Rotation reveals halo positions, not payload</dt>
              <dd>After rotation, halos are detectable. Payload recovery requires: (1) locate halos, (2) estimate rotation angle from halo geometry, (3) apply inverse rotation, (4) run Layer F decoder. Steps 2&ndash;4 are architecturally defined but not yet fully implemented.</dd>

              <dt>Blind-mode FP rate: ~30% on DIV2K</dt>
              <dd>Images with natural |R&minus;G| distribution near 168 produce off-grid detections. In manifest mode (grid check), FP rate is 0%. In blind mode, the strict detector + zone-boundary sharpness test reduces but does not eliminate FPs on high-saturation natural images.</dd>

              <dt>Does not handle crop</dt>
              <dd>Layer H handles crop forensics. Layer G is complementary: G covers rotation, H covers translation/scale.</dd>

              <dt>JPEG Q40 may transition some centers to VOID</dt>
              <dd>At aggressive compression, inner disk density may drop below INNER_THRESH. These centers are detected as VOID, not PRESENT. The count is still 4/4; the state differs. This is correct behavior &mdash; compression damaged the inner signal, and the VOID state records that.</dd>

              <dt>Does not authenticate identity</dt>
              <dd>Presence of a halo proves protocol participation. Identity requires the matching service.</dd>
            </dl>
          </div>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>Encoding Surface</h2>

          <h3>Engineering History: Three Options Considered</h3>
          <p>The current two-zone encoding was reached after two failed approaches. The failure modes illuminate why the final design works.</p>

          <div className="table-wrap" style={{ marginTop: '1.5rem' }}>
            <table>
              <thead>
                <tr><th>Option</th><th>Approach</th><th>Rotation 5&deg;</th><th>JPEG Q85</th><th>Verdict</th></tr>
              </thead>
              <tbody>
                <tr><td><strong>A</strong></td><td>prevprime(d)+1 absolute pixel values</td><td style={{ color: 'var(--tamper)' }}>5% survival</td><td>N/A</td><td style={{ color: 'var(--tamper)' }}>Rejected</td></tr>
                <tr><td><strong>B</strong></td><td>Radial profile correlation (decreasing prime targets per ring)</td><td className="yes">96% Pearson r</td><td style={{ color: 'var(--tamper)' }}>FP-saturated</td><td style={{ color: 'var(--tamper)' }}>Rejected</td></tr>
                <tr><td><strong>C</strong></td><td>Two-zone density convergence INNER=168 OUTER=140</td><td className="yes">100%</td><td className="yes">100%</td><td className="yes">Adopted</td></tr>
              </tbody>
            </table>
          </div>

          <h3>Option A Failure: Absolute Values Do Not Survive Bilinear Interpolation</h3>
          <p>Each pixel in the halo region was set so that its channel difference was one above the nearest lower prime. This worked on uncompressed images and after exact-rotation angles (0&deg;, 90&deg;, 180&deg;). It failed after bilinear interpolation at all intermediate angles. Measured pixel-value survival at 5&deg;: 5.1%. At 30&deg;: 5.0%.</p>
          <p>The mechanism is the same as the M=127 chroma gravity well in Layer E: bilinear interpolation averages neighbouring pixels. A pixel with <code>|R&minus;G|=72</code> adjacent to a natural pixel with <code>|R&minus;G|=45</code> becomes approximately 58 after interpolation. <strong>Absolute values are not rotation-invariant.</strong></p>

          <h3>Option B Failure: JPEG Saturated the Outer Ring</h3>
          <p>Radial profile correlation: decreasing prime targets from inner to outer rings, detection via Pearson correlation. Survival through bilinear rotation was strong (96% Pearson r). JPEG defeated it.</p>
          <p>After Q85, the background <code>|R&minus;G|</code> distribution of natural images drifted into the outer ring&rsquo;s target range. False positives saturated detection. The lesson: <strong>encoding targets must be chosen not just for rarity in uncompressed natural images, but for rarity after JPEG quantization at the target quality level.</strong></p>

          <h3>Two-Zone Density Convergence (Current Design)</h3>
          <p>Two concentric zones with fixed prime+1 targets:</p>
          <div className="grid-2" style={{ marginTop: '1rem', marginBottom: '1.5rem' }}>
            <div className="card card-dark" style={{ borderLeft: '3px solid var(--amber)' }}>
              <h3>Inner Disk (r &le; 5px)</h3>
              <p><code>|R&minus;G| = INNER_TARGET = 168</code><br />(= 167+1, 167 prime)<br />Background rate: ~0.023%</p>
            </div>
            <div className="card card-dark" style={{ borderLeft: '3px solid var(--teal)' }}>
              <h3>Outer Ring (r &le; 10px)</h3>
              <p><code>|R&minus;G| = OUTER_TARGET = 140</code><br />(= 139+1, 139 prime)<br />Background rate: ~0.241%</p>
            </div>
          </div>
          <p>The key detection criterion is <strong>density convergence</strong>: both zones must simultaneously exceed their respective thresholds, and the inner density must exceed the outer (gradient condition, except post-JPEG where gradient inverts). This joint criterion cannot be satisfied by natural image content. Natural images that happen to have elevated <code>|R&minus;G|</code> near 168 in some region do not simultaneously have elevated <code>|R&minus;G|</code> near 140 in a precise outer ring at exactly r=5&ndash;10px.</p>
          <p>After bilinear rotation, individual pixel values are destroyed but the density distributions are preserved. If 80% of pixels in a zone are encoded near a target value, bilinear interpolation reduces the density but does not eliminate it. <strong>The bias persists in the distribution even when individual values are scrambled.</strong></p>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <h2>Four Observable States</h2>
          <p className="lead">Layer G produces one of four states at each expected sentinel position. These are the primary output and the vocabulary for forensic interpretation.</p>

          <div className="grid-2" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--pass)' }}>
              <h3 style={{ color: 'var(--pass)' }}>State B &mdash; PRESENT</h3>
              <p>Inner &ge; 0.44 &nbsp;|&nbsp; Outer &ge; 0.05 &nbsp;|&nbsp; Gradient &gt; 0</p>
              <p>Sentinel intact. Layer G participation proven.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--amber)' }}>
              <h3 style={{ color: 'var(--amber)' }}>State C &mdash; DEGRADED</h3>
              <p>Inner 0.28&ndash;0.44 &nbsp;|&nbsp; Outer &ge; 0.05 &nbsp;|&nbsp; Gradient any</p>
              <p>JPEG or benign compression reduced inner density. Consistent with Class 1 degradation. Not evidence of tampering.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--tamper)' }}>
              <h3 style={{ color: 'var(--tamper)' }}>State D&#x2082; &mdash; VOID</h3>
              <p>Inner &lt; 0.44 &nbsp;|&nbsp; Outer &ge; 0.35 &nbsp;|&nbsp; N/A</p>
              <p>Inner disk removed, outer ring intact. Force arrows point at void. May support inference of targeted inner-disk removal.</p>
            </div>
            <div className="card card-dark" style={{ borderTop: '3px solid var(--text-dim)' }}>
              <h3>State A &mdash; ABSENT</h3>
              <p>Inner &lt; 0.28 &nbsp;|&nbsp; Outer &lt; 0.05 &nbsp;|&nbsp; N/A</p>
              <p>No halo signal detected. Cannot distinguish Class 1 from Class 2 without the manifest.</p>
            </div>
          </div>

          <p style={{ marginTop: '1.5rem' }}>The VOID state (D&#x2082;) is the gravitational lensing property made operational. An adversary who removes the inner disk leaves the outer ring intact. They cannot remove the outer ring without the removal itself being detectable as a spatial anomaly &mdash; which is Layer D&rsquo;s domain. <strong>The adversary who attacks the halo is fighting two detection systems simultaneously.</strong></p>
          <p>The compressor that destroys the inner disk is constructing the VOID signal. At Q40, some centers transition from PRESENT to VOID because aggressive quantization reduces inner density. This is not a detection failure &mdash; it is the correct state. The center is still found; its state is different.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>Detection Algorithm</h2>

          <h3>Core Detection Pipeline</h3>
          <p>Detection uses a box-filter approximation of circular disk density. A naive scan would be O(H &times; W &times; halo_area). The box-filter approach achieves O(H &times; W) via convolution.</p>
          <pre><code>{`1. Build vote masks:
     inner_mask = |R-G| within VOTE_TOL of INNER_TARGET
     outer_mask = |R-G| within VOTE_TOL of OUTER_TARGET

2. Convolve with box filter (size = 2r+1):
     inner_map = uniform_filter(inner_mask, 2*INNER_RADIUS+1) * area_correction
     outer_map = uniform_filter(outer_mask, 2*HALO_RADIUS+1)  * area_correction

3. Candidate detection:
     present_cand = (inner_map >= INNER_THRESH)
                  & (outer_map >= OUTER_THRESH)
                  & ((inner_map - outer_map) >= GRADIENT_MIN)
     void_cand    = (inner_map < INNER_THRESH) & (outer_map >= VOID_OUTER_MIN)

4. Non-maximum suppression (window = NMS_WINDOW).
5. Deduplicate within INNER_RADIUS + 2.`}</code></pre>

          <h3>Rotation Matching</h3>
          <p>After detection on a rotated image, expected center positions are computed by applying the same rotation transform to the original embedding positions:</p>
          <pre><code>{`dc = cx - cx_img;  dr = cy - cy_img
exp_col =  cos(theta)*dc + sin(theta)*dr + cx_img
exp_row = -sin(theta)*dc + cos(theta)*dr + cy_img

Match if distance(detected, expected) <= MATCH_RADIUS (28px).`}</code></pre>

          <h3><span style={{ color: 'var(--amber)' }}>○</span> Manifest-Mode FP Filtering</h3>
          <p>When embedding positions are known, off-grid detections are not claimed as halos. The grid check partitions all detections into on-grid (within <code>GRID_TOL</code> of a known center) and off-grid. Off-grid count is the honest FP measure. <strong>Manifest mode achieves 0% FP on DIV2K.</strong></p>

          <h3><span style={{ color: 'var(--teal)' }}>&bull;</span> Blind-Mode FP Filtering</h3>
          <p>Without a manifest, two mechanisms filter FPs before grid inference:</p>
          <div className="grid-2" style={{ marginTop: '1rem', marginBottom: '1.5rem' }}>
            <div className="card card-dark">
              <h3>Strict Detector</h3>
              <p><code>STRICT_INNER = 0.55</code> raises the inner threshold above the natural FP ceiling (0.471 measured on DIV2K). Eliminates ~70% of FP candidates.</p>
            </div>
            <div className="card card-dark">
              <h3>Zone-Boundary Sharpness</h3>
              <p>Compute mean(<code>|R&minus;G|</code>, r&le;5) &minus; mean(<code>|R&minus;G|</code>, 5&lt;r&le;10). Embedded halos: step &asymp;28 counts. Natural content: step &asymp;0&ndash;6 counts. Threshold = 10 provides clean separation.</p>
            </div>
          </div>
          <p>Remaining blind-mode FPs (~30% of DIV2K images) are images with large saturated warm-toned regions where <code>|R&minus;G|</code> naturally clusters near 168. These do not produce incorrect provenance claims in manifest mode.</p>

          <h3>Edge-Guided Center Selection</h3>
          <p>FPs cluster in smooth, low-edge regions &mdash; exactly the areas that provenance embedding should avoid. The <code>edge_guided_pick_centers()</code> function selects embedding positions above the image&rsquo;s own 60th percentile edge density. Since the detection filter applies the same edge criterion, positions ineligible for embedding are ineligible for detection. This is format-agnostic: edge density generalises across JPEG, HEIC, WebP, PNG, and video frames.</p>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>Protocol Constants</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Constant</th><th>Value</th><th>Derivation</th></tr>
              </thead>
              <tbody>
                <tr><td><code>HALO_RADIUS</code></td><td>10 px</td><td>Outer boundary of the lensing field. Sets detection window size.</td></tr>
                <tr><td><code>INNER_RADIUS</code></td><td>5 px</td><td>Inner disk boundary. Separates the two encoding zones.</td></tr>
                <tr><td><code>INNER_TARGET</code></td><td>168</td><td>= 167+1 (167 prime, above FLOOR=43). ~0.023% background rate in natural images.</td></tr>
                <tr><td><code>OUTER_TARGET</code></td><td>140</td><td>= 139+1 (139 prime). ~0.241% background rate in natural images.</td></tr>
                <tr><td><code>VOTE_TOL</code></td><td>8 counts</td><td>Tolerance window for target matching after JPEG quantization drift.</td></tr>
                <tr><td><code>INNER_THRESH</code></td><td>0.44</td><td>Minimum inner disk density for PRESENT or VOID. Above natural FP ceiling (0.11).</td></tr>
                <tr><td><code>OUTER_THRESH</code></td><td>0.05</td><td>Minimum outer ring density. Kept loose: JPEG kills outer; inner is primary.</td></tr>
                <tr><td><code>VOID_OUTER_MIN</code></td><td>0.35</td><td>Minimum outer density for VOID state (force-arrow).</td></tr>
                <tr><td><code>GRADIENT_MIN</code></td><td>&minus;0.50</td><td>Effectively disabled. JPEG inverts the inner&ndash;outer gradient.</td></tr>
                <tr><td><code>NMS_WINDOW</code></td><td>21 px</td><td>Non-maximum suppression window for peak detection.</td></tr>
                <tr><td><code>MATCH_RADIUS</code></td><td>28 px</td><td>Max distance from expected position for matched detection.</td></tr>
                <tr><td><code>STRICT_INNER</code></td><td>0.55</td><td>Inner threshold for strict detector. Above natural FP ceiling; below Q85 floor.</td></tr>
                <tr><td><code>FLOOR</code></td><td>43</td><td>GRANITE protocol minimum prime (sentinel entry constant M=31 + margin).</td></tr>
                <tr><td><code>EDGE_PERCENTILE</code></td><td>60</td><td>Embed only at positions above this percentile of the image&rsquo;s own edge distribution.</td></tr>
              </tbody>
            </table>
          </div>
          <p>The choice of <code>INNER_TARGET = 168</code> and <code>OUTER_TARGET = 140</code> was reached after calibration against DIV2K. Diagnostics showed: natural max inner disk density 1.541 at old target 98 &mdash; higher than the embedded signal (1.031). No threshold could separate them. Moving to 168/140 reduced the natural background to 0.023%/0.241%, giving a 9&times; gap. The value M=127 is permanently excluded from all GRANITE prime targets: it is the JPEG chroma quantization gravity well.</p>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>Survivability Profile</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Transform</th><th>Outcome Class</th><th>Detection</th><th>State</th><th>Notes</th></tr>
              </thead>
              <tbody>
                <tr><td>JPEG Q85</td>            <td style={{ color: 'var(--pass)' }}>1 &mdash; Benign</td><td className="yes">100%</td><td>B (PRESENT)</td><td>Inner density 0.31&ndash;0.52; above INNER_THRESH</td></tr>
                <tr><td>JPEG Q40</td>            <td style={{ color: 'var(--pass)' }}>1 &mdash; Benign</td><td className="yes">100%</td><td>B or D&#x2082;</td><td>2/4 centers may transition to VOID; all detected</td></tr>
                <tr><td>Rotation 0&deg;</td>     <td>1/3</td><td className="yes">100%</td><td>B</td><td>Exact pixel remap</td></tr>
                <tr><td>Rotation 15&deg;</td>    <td>1/3</td><td className="yes">100%</td><td>B</td><td>Bilinear interp; density degrades to 0.92&ndash;0.94</td></tr>
                <tr><td>Rotation 30&deg;</td>    <td>1/3</td><td className="yes">100%</td><td>B</td><td>0.92 density; 75% threshold passed</td></tr>
                <tr><td>Rotation 45&deg;</td>    <td>1/3</td><td className="yes">100%</td><td>B</td><td>0.92 density</td></tr>
                <tr><td>Rotation 90&deg;</td>    <td>1/3</td><td className="yes">100%</td><td>B</td><td>Exact pixel remap</td></tr>
                <tr><td>Rotation 180&deg;</td>   <td>1/3</td><td className="yes">100%</td><td>B</td><td>Exact pixel remap</td></tr>
                <tr><td>Force arrow (VOID)</td>  <td style={{ color: 'var(--tamper)' }}>3 indicator</td><td className="yes">100%</td><td>D&#x2082; (VOID)</td><td>Inner wiped, outer intact; force arrows persist</td></tr>
                <tr><td>Full wipe</td>           <td style={{ color: 'var(--tamper)' }}>3 indicator</td><td>0 det.</td><td>A (ABSENT)</td><td>Both zones restored; clean State A; no false claim</td></tr>
                <tr><td>Crop (any)</td>          <td>Use Layer H</td><td>N/A</td><td>N/A</td><td>Layer H handles geometry; Layer G handles rotation</td></tr>
                <tr><td>PNG (lossless)</td>      <td style={{ color: 'var(--pass)' }}>1</td><td className="yes">100%</td><td>B</td><td>Zero degradation</td></tr>
              </tbody>
            </table>
          </div>
          <blockquote style={{ marginTop: '1.5rem' }}>
            <p><em>JPEG and bilinear interpolation destroy absolute values. Density distributions survive both. The gap between marked and clean is 0.9988. The distributions do not touch.</em></p>
          </blockquote>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>Integration</h2>

          <h3>Position in Embedding Pipeline</h3>
          <p>Layer G is applied after Layer F (Payload). Layer F establishes sentinel positions. Layer G wraps those positions with the halo field. Layer H (Ruler) is applied after Layer G, since Layer H operates on final pixel values.</p>
          <p>Embedding order: <strong>A &rarr; BC &rarr; D (measurement only) &rarr; E &rarr; F &rarr; G &rarr; H.</strong></p>

          <h3>Position in Detection Pipeline</h3>
          <p>Layer G runs after Layer E provides candidate sentinel positions. In manifest mode, positions are known; Layer G evaluates state at those positions. In blind mode, Layer G scans independently and its detected halo centers inform Layer E&rsquo;s sentinel location estimates.</p>
          <p>After Layer H recovers original image coordinates (in the case of a cropped image), Layer G halo positions can be re-evaluated in the original frame.</p>

          <div className="grid-2" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark">
              <h3>Inputs</h3>
              <p><strong>centers:</strong> List[(row, col)] of sentinel positions from Layer F.</p>
              <p>PIL RGB image at current state of processing.</p>
            </div>
            <div className="card card-dark">
              <h3>Outputs</h3>
              <p><strong>Per-center HaloCenter:</strong> state (PRESENT/VOID/ABSENT), inner_density, outer_density, amplitude.</p>
              <p><strong>Rotation survival:</strong> present_matched, void_matched, missed, survival_fraction per angle.</p>
              <p><strong>FP partition:</strong> on_grid / off_grid counts after grid check.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>Validation Results</h2>
          <p>All results from validation against the DIV2K training corpus. 100 images, 2K resolution. Targets: INNER_TARGET=168, OUTER_TARGET=140.</p>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Test</th><th>Result</th><th>N</th><th>Notes</th></tr>
              </thead>
              <tbody>
                <tr><td>Detection</td>                    <td className="yes">100/100 PASS</td><td>100</td><td>4/4 centers PRESENT per image</td></tr>
                <tr><td>FP (manifest, grid-checked)</td>  <td className="yes">100/100 PASS</td><td>100</td><td>off_grid = 0 for all images</td></tr>
                <tr><td>FP (blind mode)</td>              <td>~70/100</td><td>100</td><td>~30 images have natural |R-G| near 168; documented property</td></tr>
                <tr><td>Rotation 0&deg;</td>              <td className="yes">100/100 PASS</td><td>100</td><td>Exact pixel remap</td></tr>
                <tr><td>Rotation 15&deg;</td>             <td className="yes">100/100 PASS</td><td>100</td><td>Bilinear interp; density 0.92&ndash;0.94; 0 false positives</td></tr>
                <tr><td>Rotation 30&deg;</td>             <td className="yes">100/100 PASS</td><td>100</td><td></td></tr>
                <tr><td>Rotation 45&deg;</td>             <td className="yes">100/100 PASS</td><td>100</td><td></td></tr>
                <tr><td>Rotation 90&deg;</td>             <td className="yes">100/100 PASS</td><td>100</td><td>Exact pixel remap</td></tr>
                <tr><td>Rotation 180&deg;</td>            <td className="yes">100/100 PASS</td><td>100</td><td>Exact pixel remap</td></tr>
                <tr><td>Force arrow VOID</td>             <td className="yes">100/100 PASS</td><td>100</td><td>Inner wiped, outer intact; all 4 centers detected as VOID</td></tr>
                <tr><td>Full wipe (clean)</td>            <td className="yes">100/100 PASS</td><td>100</td><td>Both zones restored; 0 detections; no false provenance claim</td></tr>
                <tr><td>JPEG Q85</td>                     <td className="yes">100/100 PASS</td><td>100</td><td></td></tr>
                <tr><td>JPEG Q40</td>                     <td className="yes">100/100 PASS</td><td>100</td><td>Some centers VOID; all detected; correct behavior</td></tr>
                <tr><td>Encoding option A (rotation 5&deg;)</td> <td style={{ color: 'var(--tamper)' }}>5.1% survival</td><td>N/A</td><td>Historical: absolute values destroyed by bilinear interp</td></tr>
                <tr><td>Encoding option B (JPEG)</td>     <td style={{ color: 'var(--tamper)' }}>FP-saturated</td><td>N/A</td><td>Historical: outer ring targets common post-JPEG</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>API Reference</h2>
          <p>Module: <code>halo_div2k_test.py</code> &nbsp;|&nbsp; Standalone &nbsp;|&nbsp; BSD-2</p>

          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Function</th><th>Signature</th><th>Returns</th></tr>
              </thead>
              <tbody>
                <tr><td><code>embed_halos()</code></td><td>image, centers</td><td>PIL Image with halos embedded</td></tr>
                <tr><td><code>detect_halos()</code></td><td>image, max_centers=200</td><td>List[HaloCenter] sorted by inner_density</td></tr>
                <tr><td><code>detect_halos_strict()</code></td><td>image, max_centers=200</td><td>List[HaloCenter] with tight FP filter</td></tr>
                <tr><td><code>wipe_inner_disk()</code></td><td>marked, original, centers, radius=None</td><td>PIL Image with inner disk restored (VOID test)</td></tr>
                <tr><td><code>wipe_full_halo()</code></td><td>marked, original, centers</td><td>PIL Image with both zones restored (full wipe)</td></tr>
                <tr><td><code>rotation_survival()</code></td><td>image, centers, angle</td><td>dict: present_matched, void_matched, missed, survival_fraction</td></tr>
                <tr><td><code>grid_check_manifest()</code></td><td>detected_positions, known_centers, grid_tol=20</td><td>(on_grid, off_grid)</td></tr>
                <tr><td><code>grid_check_blind()</code></td><td>detected_positions, img_h, img_w, grid_tol=20</td><td>(on_grid, off_grid, dominant_spacing)</td></tr>
                <tr><td><code>edge_guided_pick_centers()</code></td><td>image, n, edge_percentile=60</td><td>List[(row, col)] in high-edge zones</td></tr>
                <tr><td><code>zone_step_at()</code></td><td>image, cy, cx</td><td>float &mdash; radial step at inner radius boundary</td></tr>
              </tbody>
            </table>
          </div>

          <h3>Quickstart</h3>
          <pre><code>{`from halo_div2k_test import (
    embed_halos, detect_halos, detect_halos_strict,
    wipe_inner_disk, rotation_survival,
    edge_guided_pick_centers, grid_check_manifest, HaloState,
)

# Select embedding positions in high-edge zones
centers = edge_guided_pick_centers(image, n=4, edge_percentile=60)

# Embed
marked = embed_halos(image, centers)

# Detect (manifest mode)
halos = detect_halos(marked)
for h in halos:
    print(h.state, h.inner_density, h.outer_density)

# FP check (manifest mode, grid-checked)
fps = detect_halos_strict(clean_image)
fp_pos = [(d.row, d.col) for d in fps]
_, off_grid = grid_check_manifest(fp_pos, centers)
print(f'Off-grid FPs: {len(off_grid)}')

# Rotation survival
for angle in [0, 15, 30, 45, 90, 180]:
    result = rotation_survival(image, centers, angle)
    print(angle, result['survival_fraction'])`}</code></pre>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container content-narrow">
          <h2>Known Limitations and Open Items</h2>

          <div className="grid-2" style={{ marginTop: '1.5rem' }}>
            <div className="card card-dark">
              <h3>Confirmed Limitations</h3>
              <p><strong>Blind-mode FP rate ~30% on DIV2K.</strong> Images with large warm-toned uniform regions. Manifest mode achieves 0%. The strict detector + zone-boundary sharpness test reduces but does not eliminate blind FPs. Documented property of target 168 in high-saturation photography.</p>
              <p><strong>Rotation payload recovery not yet implemented.</strong> Halo detection after rotation is complete. Recovering the Layer F payload from a rotated image requires estimating rotation angle from halo geometry and applying inverse rotation. Architecturally defined but not implemented.</p>
              <p><strong>Q40 VOID transition.</strong> Some inner disk targets transition to VOID at Q40 because INNER_TARGET=168 is near the JPEG chroma quantization grid. Detection count remains 4/4; state changes. Expected behavior.</p>
            </div>
            <div className="card card-dark">
              <h3>Open Items</h3>
              <p><strong>Rotation-corrected payload recovery.</strong> Locate halos &rarr; estimate rotation angle from pairwise geometry &rarr; inverse rotation &rarr; Layer F decoder. Closes the loop on rotation resilience as a complete provenance claim.</p>
              <p><strong>INNER_TARGET stability at Q40.</strong> Characterize the JPEG chroma quantization table at Q40 and verify 168 falls between quantization levels.</p>
              <p><strong>Scale to 500+ images.</strong> Current validation: 100 DIV2K. Extend to full 800-image set.</p>
              <p><strong>Neural codec characterization.</strong> HEIC, AVIF, WebP. Density-distribution encoding is theoretically more robust but not measured.</p>
              <p><strong>RAW/Lightroom pipeline.</strong> Shared open item with Layer H. If halo density distributions survive demosaicing, the claim extends to professional photography.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container content-narrow">
          <h2>Canonical Phrases</h2>
          <blockquote><p><em>&ldquo;The adversary who removes the sentinel leaves the field intact. The field still points at what was there.&rdquo;</em></p></blockquote>
          <blockquote><p><em>&ldquo;JPEG and bilinear interpolation destroy absolute values. Density distributions survive both.&rdquo;</em></p></blockquote>
          <blockquote><p><em>&ldquo;The gap between marked and clean is 0.9988. The distributions do not touch.&rdquo;</em></p></blockquote>
          <blockquote><p><em>&ldquo;The compressor that destroys the inner disk is constructing the VOID signal.&rdquo;</em></p></blockquote>
          <blockquote><p><em>&ldquo;127 is not a wrapping boundary. It is JPEG&rsquo;s chroma gravity well.&rdquo;</em></p></blockquote>
          <blockquote><p><em>&ldquo;Positions survive JPEG. Values do not. Density survives everything.&rdquo;</em></p></blockquote>

          <p style={{ marginTop: '3rem', textAlign: 'center', color: 'var(--text-dim)', fontStyle: 'italic' }}>Document version: 1.0 &nbsp;|&nbsp; March 2026 &nbsp;|&nbsp; Layer G (Halo) specification complete.</p>

          <div style={{ textAlign: 'center', marginTop: '2rem' }}>
            <Link href="/the-stack" className="btn btn-secondary">&larr; Back to The Stack</Link>
          </div>
        </div>
      </section>
    </>
  );
}
