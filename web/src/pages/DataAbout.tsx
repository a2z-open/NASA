import { Page, PageHero } from '../components/Shell.tsx';
import { Link } from '../router.tsx';

export function DataAbout() {
  return (
    <Page>
      <PageHero
        title="What you are looking at"
        lede="Every sky image here is a real NASA SPHEREx observation. When we add pretend sources to test the software, we always say so. When something cannot be measured, the app says that too."
        img="/img/spherex-orbit.webp"
        alt="An illustration of the SPHEREx space telescope in orbit above Earth"
        caption="SPHEREx in orbit, in an illustration by NASA/JPL-Caltech."
      />

      <div className="plain">
        <h3>How it works</h3>
        <p>SPHEREx is a NASA space telescope that photographs the whole sky in 102 infrared colours, again and again. PARALLAX lines up every image of one patch of sky and plays them in order. Anything that shifts between images stands out.</p>
        <p>Click a source and PARALLAX measures where it is in every image, fits how fast it moves and how far away it is, and builds its spectrum. The <Link href="/hunt">Planet X hunt</Link> does this for every source in a field at once.</p>

        <h3>Data</h3>
        <ul className="bullets">
          <li><strong>SPHEREx Data Release 1</strong> spectral images, SPHEREx Science Team (2026), NASA/IPAC Infrared Science Archive, <a href="https://doi.org/10.26131/IRSA678">doi:10.26131/IRSA678</a>, and <strong>Quick Release 3</strong>. Fetched live from <a href="https://irsa.ipac.caltech.edu/Missions/spherex.html">IRSA</a>.</li>
          <li><strong>Gaia DR3</strong> (Gaia Collaboration, Vallenari et al. 2023) for reference stars.</li>
          <li>The <strong>SPHEREx DR1 all-sky data cube</strong> (102 colours, from IRSA) for the spectra of cold worlds.</li>
          <li><strong>CatWISE2020</strong> (Marocco et al. 2021) to check where a mover was ten years ago; <strong>AllWISE</strong> (Cutri et al. 2013) and the <strong>2MASS</strong> Point Source Catalog (Skrutskie et al. 2006) when its service did not answer, and for where cold worlds were years ago.</li>
          <li><strong>SPIFF</strong> brown-dwarf templates (Gagné et al. 2026, <a href="https://arxiv.org/abs/2604.22012">arXiv:2604.22012</a>).</li>
          <li><strong>SIMBAD</strong> (Wenger et al. 2000) for object names and spectral types; <strong>Kirkpatrick et al. 2021</strong> for the motion of WISE 0855.</li>
          <li>Brown-dwarf candidates picked from colours by the <strong>Dark Energy Survey</strong> (Carnero Rosell et al. 2019; Dal Ponte et al. 2023) and <strong>UKIDSS</strong> (Skrzypek et al. 2016), and published types from Best et al. 2018, 2020 and 2021 and Kirkpatrick et al. 2021, all through VizieR.</li>
          <li><strong>NASA JPL Horizons</strong> (Giorgini et al. 1996) for the positions of planets and dwarf planets, and <strong>IMCCE SkyBoT</strong> (Berthier et al. 2006) for known asteroids.</li>
          <li><strong>Other telescopes, to compare and check.</strong> The sky map can show pictures from 22 more telescopes, from JWST and Hubble to Chandra and Fermi, loaded from the archives that publish them (NASA IRSA, NASA MAST, ESA ESASky, NASA HEASARC and others). "What other telescopes saw here" asks NASA's MAST and HEASARC archives and Canada's CADC (for NEOSSat) live. The methane brown dwarfs are checked with motion and colours from WISE, NEOWISE, VISTA and UKIRT. Every search on this site runs on SPHEREx images; other telescopes are used only to line images up, to check results and to compare.</li>
        </ul>
        <p className="small muted">This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, funded by the National Aeronautics and Space Administration.</p>

        <h3>Good to know</h3>
        <ul className="bullets">
          <li>Images are resampled onto one north-up grid so they line up. Measurements use the original pixels.</li>
          <li>Pictures from other telescopes are only for comparing. Each layer says which telescope and archive it comes from.</li>
          <li>Each SPHEREx image sees a slightly different colour. Brightness is only compared between images of the same colour.</li>
          <li>On charts of measurements, a dashed line is always a fitted model or a prediction, never an observation. In the game and the diagrams, dashed shows where something was before and solid where it is now.</li>
        </ul>

        <h3>Link to it or embed it</h3>
        <p>Every view has its own address. Put coordinates in the link to open any patch of sky, and add <code>embed=1</code> to show only the viewer inside another page:</p>
        <p><code>/explore?ra=331.0965&amp;dec=-56.8006&amp;fov=6&amp;embed=1</code></p>

        <h3>AI use</h3>
        <p>AI tools helped build this: Claude Code (Anthropic) wrote and tested much of the code and documents under the team's direction, and ChatGPT helped with research and planning. No AI runs inside the app. Every measurement comes from fixed code you can read.</p>

        <h3>Not NASA</h3>
        <p>PARALLAX is an independent NASA Space Apps Challenge 2026 project for the challenge “Planet X and SPHEREx”. It is not affiliated with or endorsed by NASA, JPL, Caltech or IPAC.</p>
      </div>
    </Page>
  );
}
