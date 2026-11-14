import { Page } from '../components/Shell.tsx';

export function DataAbout() {
  return (
    <Page>
      <header className="page-head">
        <p className="eyebrow">Data &amp; About</p>
        <h1>Where every number comes from</h1>
        <p className="muted lede">PARALLAX measures real NASA SPHEREx observations. It never shows simulated images as observations, and missing measurements are shown as unavailable.</p>
      </header>
      <div className="prose">
        <h2>NASA data used</h2>
        <ul className="bullets">
          <li><strong>SPHEREx Data Release 1 Spectral Images</strong> — SPHEREx Science Team (2026), NASA/IPAC Infrared Science Archive. <a href="https://doi.org/10.26131/IRSA678">doi:10.26131/IRSA678</a>. Searched through the IRSA SIA2 collection <code>spherex_dr1</code>.</li>
          <li><strong>SPHEREx Quick Release 3 Spectral Images</strong> — NASA/IPAC IRSA, SIA2 collection <code>spherex_qr3</code>; cited according to IRSA's SPHEREx data-release guidance.</li>
          <li>Cutouts come from the IRSA cutout service (<code>?center=…&amp;size=…</code> on each Level 2 image). Each file's SHA-256, retrieval URL and time are recorded.</li>
          <li>Archive: <a href="https://irsa.ipac.caltech.edu/Missions/spherex.html">IRSA SPHEREx</a> · <a href="https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/">data access documentation</a> · <a href="https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html">DR1 overview</a>.</li>
        </ul>
        <p className="small">This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, funded by the National Aeronautics and Space Administration. See the DR1 documentation for the exact acknowledgment text.</p>

        <h2>Other catalogues and methods</h2>
        <ul className="bullets">
          <li><strong>Gaia DR3</strong> (Gaia Collaboration, Vallenari et al. 2023, A&amp;A 674, A1) — reference stars for registration, catalogue context and target astrometry. <a href="https://gea.esac.esa.int/archive/">ESA Gaia archive</a>.</li>
          <li><strong>Kirkpatrick et al. 2021</strong>, ApJS 253, 7 — parallax and motion of WISE 0855−0714 (VizieR J/ApJS/253/7).</li>
          <li><strong>SPIFF</strong> — Gagné et al. 2026, “A SPHEREx Pipeline and Spectral Library for Ultracool Dwarfs”, <a href="https://arxiv.org/abs/2604.22012">arXiv:2604.22012</a>; <a href="https://github.com/jgagneastro/SPIFF">github.com/jgagneastro/SPIFF</a> (MIT). PARALLAX uses SPIFF's 102-channel binning and template library for spectral typing. We did not invent SPIFF or its methods.</li>
        </ul>

        <h2>Software</h2>
        <p>Python: Astropy, NumPy, SciPy, Photutils, FastAPI, SPIFF. Web: React, Vite, TypeScript; charts and the sky viewer are custom SVG/Canvas code.</p>

        <h2>What is shown vs what is measured</h2>
        <ul className="bullets">
          <li>Viewer images are reprojected onto a common north-up grid for display. Positions, fluxes and spectra are measured on the original pixels with the release ePSF.</li>
          <li>Fitted motion tracks are drawn dashed and labelled “fitted model”; they are never presented as observed frames.</li>
          <li>Each SPHEREx exposure samples a different wavelength at each sky position. Brightness differences between exposures are only compared at matched wavelengths.</li>
        </ul>

        <h2>AI disclosure</h2>
        <p>AI tools assisted the team: Claude Code (Anthropic) wrote and tested much of the code and documentation under human direction; ChatGPT was used for research, planning and review. No AI model runs at runtime and no AI produced any measurement, classification or result: those come from deterministic, inspectable code on archive data. See <code>AI_USAGE.md</code> in the repository.</p>

        <h2>Not NASA</h2>
        <p>PARALLAX is an independent NASA Space Apps Challenge 2026 project (Planet X and SPHEREx). It is not affiliated with or endorsed by NASA, JPL, Caltech or IPAC.</p>
      </div>
    </Page>
  );
}
