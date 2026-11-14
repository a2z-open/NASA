import { Page, PageHero } from '../components/Shell.tsx';
import { Link } from '../router.tsx';

export function DataAbout() {
  return (
    <Page>
      <PageHero
        title="What you are looking at"
        lede="Every sky image here is a real NASA SPHEREx observation. Nothing is simulated, and when something cannot be measured the app says so."
        img="/img/spherex-assembly.webp"
        alt="The SPHEREx space telescope and its cone-shaped shields in a clean room, with an engineer beside it"
        caption="SPHEREx during final assembly, March 2024."
      />

      <div className="plain">
        <h3>How it works</h3>
        <p>SPHEREx is a NASA space telescope that photographs the whole sky in 102 infrared colours, again and again. PARALLAX lines up every image of one patch of sky and plays them in order. Anything that shifts between images stands out.</p>
        <p>Click a source and PARALLAX measures where it is in every image, fits how fast it moves and how far away it is, and builds its spectrum. The <Link href="/hunt">Planet X hunt</Link> does this for every source in a field at once.</p>

        <h3>Data</h3>
        <ul className="bullets">
          <li><strong>SPHEREx Data Release 1</strong> spectral images, SPHEREx Science Team (2026), NASA/IPAC Infrared Science Archive, <a href="https://doi.org/10.26131/IRSA678">doi:10.26131/IRSA678</a>, and <strong>Quick Release 3</strong>. Fetched live from <a href="https://irsa.ipac.caltech.edu/Missions/spherex.html">IRSA</a>.</li>
          <li><strong>Gaia DR3</strong> (Gaia Collaboration, Vallenari et al. 2023) for reference stars.</li>
          <li><strong>CatWISE2020</strong> (Marocco et al. 2021) to check where a mover was ten years ago.</li>
          <li><strong>SPIFF</strong> brown-dwarf templates (Gagné et al. 2026, <a href="https://arxiv.org/abs/2604.22012">arXiv:2604.22012</a>).</li>
          <li><strong>Kirkpatrick et al. 2021</strong> for the motion of WISE 0855, and SIMBAD for object names.</li>
        </ul>
        <p className="small muted">This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, funded by the National Aeronautics and Space Administration.</p>

        <h3>Good to know</h3>
        <ul className="bullets">
          <li>Images are resampled onto one north-up grid so they line up. Measurements use the original pixels.</li>
          <li>Each SPHEREx image sees a slightly different colour. Brightness is only compared between images of the same colour.</li>
          <li>A dashed line is always a fitted model, never an observation.</li>
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
