# First build · five-target evidence log

IRSA Level 2 metadata and local playback checks are recorded here. Epoch counts are based on a 30-day-gap grouping of archive metadata. A listed archive product can still fail the footprint, quality, or wavelength checks needed for analysis.

| Target | Archive result | Science status |
|---|---|---|
| Barnard’s Star | 358 exposure records at the updated field center, in three candidate visits. The saved sequence plays one image from each earlier group. | The native ePSF screen rejected every tested D5/D6 target core. The separately screened D6 sample also had no clean nearest target pixel. The reserved target position remains unmeasured. |
| Epsilon Indi B | 465 candidate detector products. | Coverage only. Paired flux remains optional and unverified. |
| WISE 0855 | 258 candidate detector products. | Coverage only. Detection and sensitivity remain unmeasured. |
| RW Aurigae | 335 candidate detector products. | Coverage only. Variability remains unmeasured. |
| R Draconis | 539 candidate detector products. | Coverage only. Variability remains unmeasured. |

- [Barnard archive provenance and reservation](barnards-star-archive.json) records the collection counts, fit-frame IDs, native FITS SHA-256 hashes, and reserved product metadata.
- [Native D5 calibration screen](barnards-star-d5-calibration.json) records wavelength and bandwidth candidates. Its best downloaded pair overlaps in the center-and-width approximation, and both target cores carry hard-failure flags. This is display evidence and a quality rejection.
- [Native D6 calibration screen](barnards-star-d6-calibration.json) records the longer-wavelength fit-visit alternative. All 19 checked nearest cores were flagged.
- [Exploratory native fit screen](barnards-fit-screen.json) records the Gaia-assisted fit seeds, reference residuals, and quality outcomes in the first two visits. It does not provide an empirical prediction tolerance or a held-out result.

During an early local API smoke test, two later-date cutouts were rendered at RA 269.485°, Dec 4.78°, about 2.4′ from Barnard’s Star. The 2′ cutouts exclude the target. The temporary previews were cleared. The guarded lookup excludes reserved product IDs and later-visit cutouts near the target, and the saved sequence includes only earlier visits.
