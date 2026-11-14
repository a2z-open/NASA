# PARALLAX: Planet Nine / distant-world search — literature brief

Compiled 2026-11-14 from arXiv abstracts and full texts, journal pages, IRSA/SPHEREx pages and JPL Horizons.
Tags: **[derived]** = our own arithmetic from cited numbers, not a published value. **[memory]** = recalled, not re-checked. "Not confirmed" = looked for and not found. Section 8 lists every open item.

## 0. Numbers to design against

| Quantity | Value | Source |
|---|---|---|
| Distance now (what earlier surveys have not excluded) | 550 (+250/-180) AU, i.e. about 370-800 AU | Brown, Holman & Batygin 2024, arXiv:2401.17977 |
| V magnitude (same population) | 22.0 (+1.1/-1.4), i.e. about 20.6-23.1 | same |
| Reflected flux near 1 micron if the albedo is flat | 7 microJy (range 2.6-26), AB 21.75 (20.35-22.85) | [derived], section 3 |
| Six-month parallax jump at 90 deg elongation | 412,530 arcsec / d(AU): 22.9 arcmin at 300 AU, 13.8 at 500, 9.8 at 700, 6.9 at 1000 | [derived], section 2 |
| SPHEREx single exposure, 5 sigma, per channel | AB 18.5-19.0 (91-145 microJy) at 0.75-3.8 micron; AB 16.6-18.0 (229-832 microJy) at 3.8-5.0 micron | Crill et al. 2025, arXiv:2505.24856 (pre-launch) |
| SPHEREx all-sky, 4 passes in 2 years | AB 19.5-19.9 (40-58 microJy); AB 17.8-18.8 (110-275 microJy) | Bock et al. 2025, arXiv:2511.02985 |
| Best sky band | within +/-12 deg of Dec of the track RA 33,Dec -2 -> RA 60,+11 -> RA 90,+21 -> RA 107,+25 | Brown & Batygin 2021 + [derived] track |

## 1. The hypothesis and the current best estimates

**The idea.** The orbits of the most distant Kuiper belt objects point in similar directions and share a plane. Batygin & Brown put the chance of that at 0.007% and proposed an unseen planet of at least about 10 Earth masses (Batygin & Brown 2016, arXiv:1601.05438). That first planet was only notional: 10 Earth masses, eccentricity 0.7, inclination 30 deg (Brown & Batygin 2021, arXiv:2108.09868), at roughly 700 AU (Fienga et al. 2016 abstract, arXiv:1602.06116).

| Paper | Mass (Earth) | Semimajor axis (AU) | Perihelion q / aphelion Q (AU) | Inclination (deg) | Brightness, distance |
|---|---|---|---|---|---|
| Brown & Batygin 2016, arXiv:1603.05712 | 5-20 | 380-980 | q 150-350 | about 30 | 22 < V < 25 near aphelion |
| Batygin et al. 2019 review, arXiv:1902.10103 | 5-10 | 400-800 | eccentricity 0.2-0.5 | 15-25 | not in abstract |
| Brown & Batygin 2021, arXiv:2108.09868 | 6.2 (+2.2/-1.3) | 380 (+140/-80) | q 300 (+85/-60), Q 460 (+200/-110) | 16 +/- 5, node 97 | only as a figure (axes span R 16-26, 200-2000 AU) |
| Same paper, "born in a cluster" prior | 6.9 (+2.6/-1.6) | 460 (+180/-100) | not stated | 15.6 | about 1 mag fainter near aphelion |
| Brown, Holman & Batygin 2024, arXiv:2401.17977 (what is left) | 6.6 (+2.6/-1.7) | 500 (+170/-120) | Q 630 (+290/-170) | not stated | 550 (+250/-180) AU now, V 22.0 (+1.1/-1.4) |
| Siraj, Chyba & Tremaine 2025 "Planet X", arXiv:2410.18170 | 4.4 +/- 1.1 | 290 +/- 30 | q about 200 +/- 50, Q 370 +/- 30 | 6.8 +/- 5.0 | about 60% of models have V > 20 |

- Brightness assumptions in the 2021 paper: radius = (mass / 3 Earth masses) Earth radii, albedo 0.2 to 0.75. A rocky or icy "super-Eris" would be about 50% smaller and about 3 mag dimmer (Brown & Batygin 2021, arXiv:2108.09868).
- **Where to look.** About 95% of the probability lies within +/-12 deg of declination of an orbit with inclination 16 deg and ascending node 97 deg, and the density peaks near RA 45 deg, which the authors identify with aphelion (Brown & Batygin 2021, Fig. 9 caption, arXiv:2108.09868).
- Track of that orbit [derived], as ecliptic longitude/latitude -> RA/Dec in degrees: 30/-15 -> 33/-2; 45/-13 -> 46/+4; 60/-10 -> 60/+11; 75/-6 -> 74/+16; 90/-2 -> 90/+21; 105/+2 -> 107/+25. It crosses the Galactic plane at RA 90, Dec +21 (Taurus/Gemini/Orion border) and again at RA 270, Dec -21. Caution: the median longitude of perihelion of 247 deg (corner plot of the same paper) puts aphelion at RA 67, Dec +14, not RA 45. We could not resolve this, so treat RA 30-110 deg along the track as the prime band.
- Siraj et al. find their own density peak near RA 55 deg, half of their planets between RA 0 and 110 deg, and 90% within +/-10 deg of the ecliptic (Siraj, Chyba & Tremaine 2025, arXiv:2410.18170).
- SPHEREx sees ecliptic longitude L when the Sun is at L +/- 90 deg. For L = 30-105 deg that means about 20 Jan to 5 Apr and 23 Jul to 8 Oct each year, so three visits exist by Nov 2026 [derived].

**Searches already done.**
- ZTF: no candidate; 95% efficient at V = 20.5 over the northern part of the orbit; 56% of the predicted population ruled out (Brown & Batygin 2022, arXiv:2110.13117).
- DES: 10.2% ruled out, 5.0% of it new; ZTF + DES together 61.2% (Belyakov, Bernardinelli & Brown 2022, arXiv:2203.07642, as summarised in arXiv:2401.17977).
- Pan-STARRS1: sky north of Dec -30 deg, at least 9 detections linked by orbit fitting, 50% complete at V = 21.5 (median limit V = 21.0 outside the Galactic plane). With ZTF and DES, 78% is ruled out (Brown, Holman & Batygin 2024, arXiv:2401.17977).
- What is left: a large area near the northern Galactic plane where the planet would be near aphelion and faint, a smaller patch of the southern Galactic plane, and a strip south of Dec -30 deg (same paper). No RA/Dec bounds are given in its text.
- Planetary ephemeris: a 5 Earth-mass planet cannot be closer than 500 AU, and a 10 Earth-mass one cannot be closer than 650 AU (Fienga et al. 2020, A&A 640, A6).

**2025-2026 updates.**
- 2017 OF201: semimajor axis about 830 AU, perihelion 45 AU, about 700 km across, now near 90 AU. Its perihelion direction falls outside the cluster (Cheng, Li & Yang 2025, arXiv:2505.15806). 2023 KQ14 "Ammonite", the fourth sednoid: perihelion about 66 AU, semimajor axis about 252 AU, not aligned with the other sednoids (Nature Astronomy, July 2025; numbers from press coverage, Astronomy.com).
- "Planet Y": the mean plane of the Kuiper belt looks warped at 80-400 AU (98% confidence) and 80-200 AU (96%). A body between Mercury and Earth in mass at 100-200 AU, inclined by 10 deg or more, could do it (Siraj, Chyba & Tremaine 2025, arXiv:2508.14156). With the sample grown from 21 to 25 objects, the clustering significance falls from 2.7 to 1.9 sigma (Siraj, Chyba & Tremaine 2026, arXiv:2604.25990).
- In favour: low-inclination Neptune-crossing objects reject a no-planet model at about 5 sigma (Batygin et al. 2024, arXiv:2404.11594).
- Rubin: the LSST officially began on 29 June 2026 (Newswise 2026). Its single-image limit of r about 24.3 covers much of the predicted range but not the most northern part of the path (Brown & Batygin 2021, arXiv:2108.09868). We found no peer-reviewed detection as of Nov 2026.

**Main criticisms.** The clustering may be a selection effect of where and when surveys looked.
- OSSOS: its 8 large-orbit objects are consistent with a uniform distribution once the survey's biases are modelled (Shankman et al. 2017, arXiv:1706.05348).
- DES + OSSOS + Sheppard-Trujillo: 14 extreme objects are consistent with uniform at the 17-94% level (Napier et al. 2021, arXiv:2102.05601).
- The reply: an analysis of all detections gives only a 0.2% chance of a uniform population, and those surveys are too narrow to see the clustering (Brown & Batygin 2021, arXiv:2108.09868, citing their 2019 paper).

## 2. How professionals search

- **Tracklet linking.** Detect sources in single exposures, join same-night pairs into tracklets, then link tracklets across nights with an orbit fit. HelioLinC assumes a trial distance, moves every tracklet to a Sun-centred frame and clusters them, at a cost of N log N instead of N cubed. It linked about 41,000 new minor planets from archival data (Holman et al. 2018, arXiv:1805.02638).
- **Shift-and-stack.** Shift images along a trial motion and add them, so a source too faint for one frame builds up. On TESS full-frame images this reaches about magnitude 22 (Holman, Payne & Pal 2019, arXiv:1910.06383), or I about 22.0 +/- 0.5 from roughly 1,300 exposures per sector (Payne, Holman & Pal 2019, arXiv:1911.03676).
- A TESS test on Sectors 18-19 searched 70-800 AU and recovered known objects including Sedna (V 20.64), with reliable recovery for V < 21 and distances up to about 150 AU (Rice & Laughlin 2020, arXiv:2010.13791).
- **WISE, which also observes at 90 deg elongation.** Luhman used multi-epoch astrometry to look for parallax motion over the whole sky. Nothing was found down to W2 = 14.5, which excludes a Saturn analog within 28,000 AU and a Jupiter analog within 82,000 AU (Luhman 2014, ApJ 781, 4).
- Meisner et al. 2017: one-day W1 coadds over about 2,000 square degrees, complete to W1 < 16.66 (90%). Coadds reach about 800 AU where single exposures reach about 430 AU. No candidate (Meisner et al. 2017, arXiv:1611.00015).
- Meisner et al. 2018: 31,480 square degrees (76.3% of the sky), data from 2010 to 2016. Method: difference each one-day coadd against a template taken more than 5 months away, extract transients, link them with a "reflex motion plus linear drift" model and then a full orbit fit. Depth W1 = 16.70 (90% complete), sensitive to about 250-800 AU near the ecliptic. No linkage of 5 or more detections survived. Not searched: ecliptic latitude above 55 deg and the inner Galaxy (Meisner et al. 2018, arXiv:1712.04950).
- **Far-infrared.** IRAS 1983: one candidate at B1950 RA 314.835, Dec +64.215 and, 20.3 arcmin away 11.9 weeks later, RA 314.074, Dec +64.149 (about RA 315.1, Dec +64.4 in J2000 [derived]). Suggested distance 225 +/- 15 AU, mass 3-5 Earth masses, Galactic latitude 9 deg in strong cirrus, "not overwhelming" (Rowan-Robinson 2022, arXiv:2111.03831).
- IRAS + AKARI: pairs 42 to 69.6 arcmin apart over 23 years (500-700 AU, 7-17 Earth masses). One candidate survived. IRAS F02211-4844 at **RA 35.74075, Dec -48.5125** (scans 26 Jun to 1 Sep 1983; 0.24 Jy at 60 micron, 0.52 Jy at 100). AKARI-MUSL J0220440-491247 at **RA 35.18379, Dec -49.2135** (26 Jun and 26 Dec 2006; 0.27 Jy at 90 micron). Separation 47.46 arcmin. No orbit or mass was fitted (Phan et al. 2025, PASA 42, e064, arXiv:2504.17288).
- About that candidate [derived]: its ecliptic latitude is -57 deg, far outside the +/-12 deg band above. A straight-line extrapolation to mid-2026 gives roughly RA 34.7, Dec -49.8, uncertain by at least 0.3 deg. SPHEREx views it in late June and late December.
- AKARI alone, objects still over 24 hours but moved after six months, in 30 < RA < 50, -20 < Dec < +20: two candidates, no coordinates in the abstract (Chen et al. 2025, arXiv:2506.12854).
- **Millimetre.** ACT searched 300-2000 AU with motions up to 6.3 arcmin per year. About 3,500 tentative candidates, none significant. Limits are 4-12 mJy at 150 GHz for 300-600 AU: a 5 Earth-mass planet is detectable to 325-625 AU and a 10 Earth-mass one to 425-775 AU. That removes about 17% and 9% of parameter space (Naess et al. 2021, ApJ 923, 224).
- **Ground-based parallax.** Sources that shift between consecutive nights by the expected parallax, over 98 square degrees to r 21.0-21.4: none found (Socas-Navarro & Trujillo 2025, arXiv:2504.05473). At opposition the parallax motion shows within 24 hours (Brown & Batygin 2016, arXiv:1603.05712).

**What parallax looks like at 300-1000 AU [derived].** Earth moves 3,548 arcsec per day as seen from 1 AU. An object at d AU traces a yearly ellipse of half-width 206,265/d arcsec.

| d (AU) | Yearly half-width | Rate at opposition | Six-month jump between quadratures | In SPHEREx pixels | Own orbital drift (circular) |
|---|---|---|---|---|---|
| 300 | 11.5 arcmin | 11.1 arcsec/day | 1375 arcsec = 22.9 arcmin | 224 | 249 arcsec/yr |
| 500 | 6.9 arcmin | 6.8 arcsec/day | 825 arcsec = 13.8 arcmin | 134 | 116 arcsec/yr |
| 700 | 4.9 arcmin | 4.9 arcsec/day | 589 arcsec = 9.8 arcmin | 96 | 70 arcsec/yr |
| 1000 | 3.4 arcmin | 3.4 arcsec/day | 413 arcsec = 6.9 arcmin | 67 | 41 arcsec/yr |

- At exactly 90 deg elongation Earth moves along the line of sight, so the leftover parallax rate is 3,548 x sin(ecliptic latitude) / d arcsec per day, directed along ecliptic latitude. At 500 AU that is 1.2 arcsec/day at latitude 10 deg and 2.4 at 20 deg, or at most about 34 arcsec (5.5 pixels) over a two-week visit. Published check: a body at 400 AU moves 1.6 arcsec per one-day WISE epoch at latitude 10 deg (Meisner et al. 2018, arXiv:1712.04950). Our formula gives 1.5.
- Between two visits six months apart Earth has moved 2 AU sideways, so the object jumps 2/d radians along ecliptic longitude and then jumps back. The jump size gives the distance directly; the difference between successive jumps gives the orbital drift.

## 3. Predicted brightness from 0.75 to 5 micron

**Reflected sunlight, flat albedo [derived].** Take V = 22.0.
1. V on the Vega scale is within about 0.02 mag of AB, so flux at 0.55 micron = 3631 Jy x 10^(-0.4 x 22.0) = 5.8 microJy.
2. Sunlight is brighter per unit frequency near 1 micron: the Sun's AB colour is V - z = 0.30 and V - J = 0.26 [memory: Willmer 2018 solar magnitudes]. So AB(1 micron) = V - 0.25 = 21.75.
3. Flux = 3631 Jy x 10^(-0.4 x 21.75) = **7.2 microJy**. For V = 20.6 it is 26 microJy (AB 20.35). For V = 23.1 it is 2.6 microJy (AB 22.85).
4. Further out the Sun fades: AB = V + 1.1 at 3.4 micron and V + 1.75 at 4.6 micron [memory, same source], so about 2.1 and 1.1 microJy for V = 22.0.

**Model atmospheres say the near-infrared is darker than that.**
- Fortney et al. 2016 (arXiv:1604.07424): effective temperature at most 35-50 K for 5-20 Earth masses, radius 3-6 Earth radii. Methane freezes out, leaving a Rayleigh-scattering albedo near 0.75 in visible light (fiducial V = 21.6 for 10 Earth masses at 622 AU). The 3-5 micron flux is about 20 orders of magnitude above a blackbody.
- Their Table 2, at 622 AU: r 21.3-21.4, z 21.2-22.5, J 23.7-24.6, H 23.4-24.9, K 30.4-31.0. The magnitude system is not stated. Read as Vega [derived], these are z about 2-7 microJy, J and H about 0.1-0.5 microJy, K nothing. The planet is blue: visible to 1 micron, then nearly dark until a 3-5 micron window.

| Fortney model at 622 AU | W1 (3.4 micron) | W2 (4.6 micron) | In microJy [derived, WISE Vega zero points] |
|---|---|---|---|
| 40 K, methane 0.1 x solar | 27.6 | 23.2 | 0.003 / 0.09 |
| 40 K, methane 1e-6 | 20.5 | 22.8 | 1.9 / 0.13 |
| 50 K, methane 1e-3 | 19.0 | 17.2 | 7.8 / 23 |
| 50 K, methane 1e-6 (brightest W1) | 16.1 | 17.2 | 112 / 23 |
| 60 K, methane 0.1 (hotter than expected) | 27.5 | 13.7 | 0.003 / 569 |

- Linder & Mordasini 2016 (arXiv:1602.07465), blackbody plus Neptune-like albedo 0.41: a 10 Earth-mass planet at 700 AU has 47 K, 3.7 Earth radii, V 21.7, R 21.4, I 21.0, W1 20.1, W2 20.1, W3 18.6, W4 10.2. That is 2.8 and 1.6 microJy in W1 and W2 [derived]. For 5 / 20 Earth masses at 700 AU, V = 22.3 / 21.3. Thermal emission wins only beyond about 13 micron.
- Ginzburg, Sari & Loeb 2016 (ApJ 822, L11): the planet is powered by its own cooling, not sunlight, with effective temperature about 50 K that depends only weakly on envelope mass. A companion paper puts it at 28-53 K with the blackbody peak at 50-100 micron (Cowan, Holder & Kaib 2016, arXiv:1602.05963). Scaling: reflected light falls as distance^-4, thermal emission as distance^-2 (Linder & Mordasini 2016; Chen et al. 2025).

## 4. SPHEREx facts that matter

- 102 channels from 0.75 to 5.0 micron, resolving power 35-130, 6.2 arcsec pixels, six 2048 x 2048 detectors, launched 11 March 2025, science observations from 1 May 2025 (Bock et al. 2025, arXiv:2511.02985).
- Resolving power by band: 39, 41, 41, 35 (bands 1-4, to 3.8 micron) and 112, 128 (bands 5-6, 3.8-5.0 micron). 17 channels per detector. Pixel 6.12-6.15 arcsec. Field 3.5 x 11.3 deg (Crill et al. 2025, arXiv:2505.24856).
- Exposure 116.9 s in flight (Bock et al. 2025); 112.5 s assumed before launch (Crill et al. 2025). Image sharpness: better than 3 arcsec FWHM over most of the short-wave arrays, up to 5.5 arcsec in the mid-wave ones (Bock et al. 2025).
- **Geometry.** Exposures lie close to the great circle 90 deg from the Sun. The Sun is kept at least 91 deg (93.5 deg in survey planning) from the shield axis. Sun-synchronous orbit, about 650 km. A typical object is seen in all channels within about two weeks per survey. Four all-sky surveys in 25 months, so each position returns about every six months (Bock et al. 2025; Crill et al. 2025; spherex.caltech.edu survey page).
- **Depth, 5 sigma per channel, no confusion noise included.**
  - Single visit, pre-launch: AB 18.5-19.0 (91-145 microJy) at 0.75-3.8 micron and AB 16.6-18.0 (229-832 microJy) at 3.8-5.0 micron, set by zodiacal light (Crill et al. 2025, abstract and Fig. 17).
  - All-sky after four passes: AB 19.5-19.9 (40-58 microJy) and AB 17.8-18.8 (110-275 microJy). In-flight median 19.7 against a requirement of 18.4 (Bock et al. 2025). Four passes are "exactly a factor 2 deeper" than one (Crill et al. 2025), so the in-flight single visit is about AB 18.75-19.15 [derived].
  - Deep fields: two fields of about 100 square degrees at the ecliptic poles, more than 400 observations per channel at the centre, 10-20 times deeper than a single visit (Bock et al. 2025; Crill et al. 2025). That is about AB 21.6 per channel below 3.82 micron (quoted in arXiv:2403.19740). They are at ecliptic latitude 90 deg, far from the Planet Nine band.
- **Data.** Weekly image releases at IRSA within two months of acquisition: QR1 from July 2025 (retired), QR2 from October 2025, QR3 from September 2026, DR1 in November 2026 (IRSA Quick Release overview).
- **Solar-system plans.** About 100,000 asteroids with useful fluxes and about 10,000 good spectra, with a call to run forced photometry on every object with a known orbit (Ivezic et al. 2022, Icarus 371, 114696). A Solar System catalog is due in May 2028 (Bock et al. 2025). It is expected to hold hundreds of thousands of objects (Lisse, Bauer & Kim 2024, arXiv:2402.08705).
- Published results so far: water, CO2 and CO in interstellar comet 3I/ATLAS (Lisse et al. 2025, arXiv:2512.07318), and a forced-photometry tool for fast-moving point sources, which reaches signal-to-noise above 10 per channel for W2 of 14.0 or brighter (Gagne et al. 2026, arXiv:2604.22012).
- **We found no published SPHEREx search for Planet Nine or for unknown moving objects.** The mission overview does not mention Planet Nine (Bock et al. 2025).

## 5. Honest feasibility

All rows are [derived] from the numbers in sections 3 and 4. Positive values mean "too faint by this many magnitudes".

| Scenario | Flux (microJy) | vs single exposure at 0.75-3.8 micron (91-145 microJy) | vs single exposure at 3.8-5.0 micron (229-832 microJy) | vs 140 microJy per-visit stack (AB 18.53) |
|---|---|---|---|---|
| Nominal V = 22.0, flat albedo, at 1 micron | 7.2 | 2.8-3.3 | n/a | n/a |
| Brightest remaining case, V = 20.6, at 1 micron | 26 | 1.4-1.8 | n/a | n/a |
| Faint case, V = 23.1, at 1 micron | 2.6 | 3.9-4.3 | n/a | n/a |
| Nominal, reflected light at 4.6 micron | 1.1-1.6 | n/a | 5.4-7.2 | 4.9-5.3 |
| Fortney 50 K models, thermal, W2 = 17.2 | 23 | n/a | 2.5-3.9 | 2.0 |
| Fortney 40 K models, thermal, W2 = 22.8-23.2 | 0.09-0.13 | n/a | above 8 | 7.6-8.0 |
| Fortney brightest W1 = 16.1, at 3.4 micron | 112 | -0.2 to +0.3 | n/a | n/a |
| Fortney 60 K, W2 = 13.7 | 569 | n/a | -1.0 to +0.4 | -1.5 (detectable) |

- **Verdict.** A nominal Planet Nine is about 3 mag (a factor of 13-20) below one SPHEREx exposure near 1 micron. At 3.8-5.0 micron it is 2 mag below the 140 microJy stack in the kindest 50 K model, about 5 mag below it in reflected light, and about 8 mag below it in the 40 K models. SPHEREx alone will not find the nominal planet.
- **Best case with stacking.** Adding the 17 channels of band 1 (0.75-1.1 micron, where a gas-rich planet still reflects) over four passes gives about (40-58)/sqrt(17) = 10-14 microJy, or AB 21.0-21.4, roughly V 21.3-21.7 for a flat albedo. On paper that matches Pan-STARRS (V 21.5) and covers the whole sky. In practice it will be shallower: a blind search over many trial distances needs a threshold above 5 sigma, and confusion is ignored. A nominal planet (2-7 microJy in z) would sit at signal-to-noise 1-4.
- **What SPHEREx could detect or exclude.**
  1. Bodies with V of about 21 or brighter (ideal case) in places optical surveys covered poorly: south of Dec -30 deg and parts of the Galactic plane, where SPHEREx confusion is also worst.
  2. The Rowan-Robinson candidate: 3-5 Earth masses at 225 AU would be about V 19 for 1.5 Earth radii and albedo 0.3, near the single-exposure limit, with a 0.5 deg six-month jump.
  3. The bright end of "Planet Y": an Earth-size body at 150 AU with albedo 0.3 would be about V 18. A Mercury-size one at 200 AU would be about V 23 and out of reach.
  4. The bright end of the Phan et al. candidate: 7-17 Earth masses at 500-700 AU spans about V 18.6-23.5 under the 2021 radius and albedo assumptions.
  5. Methane-poor "bright window" models: stacking about 8 channels across 3.0-3.6 micron over four passes gives about 14-20 microJy, equivalent to W1 of about 17.9-18.3. That is roughly 1.2-1.6 mag beyond the WISE limit of 16.7, and it includes the 24% of sky WISE did not search. This is idealised and ignores confusion.
  6. Already excluded by WISE, so only a cross-check: anything with W2 brighter than 14.5 (Luhman 2014), which includes the 60 K model.
- **What would be needed.** About 0.4-2 mag more depth than that ideal stack, which is 2 to 40 times more exposure. The orbit can support more than 15 years of operations (Bock et al. 2025), but 8 years instead of 2 buys only 0.75 mag. More realistic roles: (a) spectral vetting of candidates found by Rubin, which reaches r about 24.3 per image; (b) a uniform all-sky limit near V 21 for slow movers; (c) joining SPHEREx detections to WISE/NEOWISE positions from 2010-2024 for long-baseline orbits.

## 6. Known distant bodies for validating a parallax search

Geocentric values from JPL Horizons (queried 2026-11-14; ephemeris 1 May 2025 to 31 Dec 2026). "Quadrature" is the date when solar elongation is 90 deg, which is when SPHEREx sees the body. V is the Horizons model magnitude.

| Body | V | Sun distance mid-2026 (AU) | RA, Dec on 1 Jul 2026 (deg) | Ecliptic latitude | Rate at quadrature | Drift over +/-7 days | Six-month jumps (alternating) | Quadrature dates |
|---|---|---|---|---|---|---|---|---|
| Pluto | 14.5 | 35.55 | 307.93, -23.23 | -4.2 | 0.79-0.87 arcsec/hr (19-21 per day) | 265-293 arcsec | 144 / 245 arcmin | 2025-10-25, 2026-04-26, 2026-10-27 |
| Makemake | 17.1 | 52.73 | 200.59, +20.83 | +27.2 | 1.29-1.37 (31-33) | 431-460 | 105 / 156 | 2025-07-01, 2026-01-03, 2026-07-03 |
| Haumea | 17.3 | 49.78 | 219.45, +14.61 | +28.4 | 1.44-1.48 (34.5-35.5) | 482-495 | 110 / 166 | 2025-07-24, 2026-01-24, 2026-07-25 |
| Eris | 18.7 | 95.48 | 27.46, +0.15 | -10.4 | 0.21-0.38 (5.0-9.1) | 69-128 | 66 / 79 | 2025-07-18, 2026-01-15, 2026-07-19 |
| Quaoar | 18.7-18.9 | 42.61 | 281.63, -14.80 | +8.2 | 0.75-0.78 (18.0-18.7) | 252-262 | 122 / 200 | 2025-10-02, 2026-04-02, 2026-10-04 |
| Gonggong | 21.5 | 89.81 | 338.17, -9.99 | -0.8 | 0.13-0.16 (3.1-3.9) | 44-55 | 69 / 85 | 2025-05-27, 2025-11-27, 2026-05-28, 2026-11-28 |
| Orcus | 19.1 | 47.99 | 159.37, -12.99 | -20.1 | 1.08-1.17 (26-28) | 363-393 | 115 / 173 | 2025-06-06, 2025-12-10, 2026-06-07, 2026-12-11 |
| Sedna | 20.8 | 82.90 | 62.01, +9.01 | -11.7 | 0.42-0.44 (10.1-10.5) | 141-146 | 65 / 102 | 2025-08-25, 2026-02-19, 2026-08-26 |

- The mean of the two jumps equals 2 AU / distance: Pluto 193 arcmin, Quaoar 161, Orcus 143, Haumea 138, Makemake 130, Sedna 83, Gonggong 77, Eris 72 [derived]. Half the difference is the body's own six-month orbital motion.
- Rates near quadrature are not the minimum. Each body passes a stationary point about 10 days away (Pluto falls to 0.07 arcsec/hr). High-latitude bodies such as Makemake and Haumea never go below about 1.2 arcsec/hr, because the leftover parallax rate scales with sin(latitude).
- Expected SPHEREx signal-to-noise per channel in one exposure, flat albedo [derived]: Pluto 250-400, Makemake and Haumea 20-35, Eris and Quaoar 4-9, Orcus 4-6, Sedna about 1, Gonggong about 0.5. Stacking 68 channels lifts Sedna to 6-10 and Gonggong to 3-5. Sedna, Gonggong and Quaoar are very red, so they should do better than this.
- Sedna lies inside the Planet Nine band (RA 62, Dec +9) and is the best end-to-end test of stacking plus the parallax jump. JWST spectra over 0.7-5.2 micron give the expected features: ethane, water ice and a broad 2.7-3.6 micron organic absorption on Sedna, Gonggong and Quaoar, with CO2 and methane bands on some (Emery et al. 2024, arXiv:2309.15230).

## 7. Ideas a 102-channel survey at fixed 90 deg elongation adds

1. **Zig-zag distance test.** Pair detections from consecutive visits separated by 6.9-22.9 arcmin along ecliptic longitude (300-1000 AU), then require the third visit to land back near the first position plus twice the orbital drift. One free parameter, distance, explains three epochs. WISE searches fit the same "reflex plus drift" model (Meisner et al. 2018), but SPHEREx delivers a full spectrum at every epoch.
2. **Template-weighted multi-channel stack within a visit.** The 102 channels arrive over about two weeks, while a body beyond 300 AU drifts by about 1 arcmin at most (300 AU, latitude 20 deg) in a direction fixed by sky position, date and trial distance. Shift by that known vector for about 10 trial distances, then add channels weighted by a spectrum template: Rayleigh-blue for a gas planet, the 3.0-3.6 micron window, or flat for an icy body. The gain is up to the square root of the number of channels used.
3. **Six-month self-differencing.** Subtract the stack from visit N+1 from visit N. Stars and galaxies cancel, and a distant body leaves a positive and a negative image separated by the parallax jump. This attacks confusion noise from 6.2 arcsec pixels, the main obstacle in the Galactic plane where most remaining probability lies.
4. **Spectral vetting.** A cold gas-rich planet is bright to 1 micron, about 2 mag fainter in J and H, absent at K, with a possible 3-5 micron window (Fortney et al. 2016, Table 2). An icy dwarf shows methane-ice bands near 1.7, 2.3 and 3.3 micron, water ice near 1.5, 2.0 and 3.0, and CO2 near 4.27 [memory: laboratory band positions]. Stars and galaxies show neither pattern, and main-belt asteroids rise steeply past 3.5 micron from their own heat. No earlier Planet Nine search could classify a candidate from discovery data alone.
5. **Fill the gaps and test the published candidates.** SPHEREx covers the areas the WISE search dropped (ecliptic latitude above 55 deg, inner Galaxy) and the Pan-STARRS gap south of Dec -30 deg. It can re-observe the Phan et al. position (about RA 34.7, Dec -49.8 in 2026) and the Rowan-Robinson field (about RA 315.1, Dec +64.4, search radius about 5 deg).

## 8. Not confirmed, and caveats

- Brown & Batygin 2021 give magnitude and distance against RA only as a figure. The V range used here is for the population left after the 2024 search.
- Peak sky position: the paper's caption says RA about 45 deg, our geometry from its median angles says RA about 67 deg. Unresolved.
- The Pan-STARRS paper gives no RA/Dec bounds for what is left. The Galactic-plane crossings quoted are [derived].
- Fortney et al. Table 2 does not state its magnitude system. We read W1 and W2 as Vega, as Meisner et al. 2018 do, and assumed Vega for the other bands.
- SPHEREx in-flight single-exposure depth per channel is shown only in a figure. Single-visit numbers here are pre-launch or [derived]. No depth includes confusion noise.
- Phan et al. publish no orbit, distance or mass for their candidate. The 2026 position is our straight-line extrapolation. The Rowan-Robinson J2000 position is our approximate precession.
- Solar colours, ice-band wavelengths and SPHEREx band edges (band 1 = 0.75-1.1 micron) are [memory]. "Ammonite" numbers come from press coverage. The 700 AU figure for the 2016 planet comes from another paper's abstract.
- No peer-reviewed probability that Rubin finds Planet Nine was found.
- Horizons V magnitudes are model values. Expect errors of 0.1-0.3 mag and real colour differences.
- All stacking depths in section 5 assume ideal square-root-of-N gains.

## References

- Batygin & Brown 2016, Evidence for a Distant Giant Planet in the Solar System: https://arxiv.org/abs/1601.05438 ; Brown & Batygin 2016, Observational constraints on the orbit and location of Planet Nine: https://arxiv.org/abs/1603.05712
- Batygin, Adams, Brown & Becker 2019, The Planet Nine Hypothesis (Physics Reports): https://arxiv.org/abs/1902.10103
- Brown & Batygin 2021, The Orbit of Planet Nine (AJ 162, 219): https://arxiv.org/abs/2108.09868
- Brown & Batygin 2022, A search for Planet Nine using the ZTF public archive: https://arxiv.org/abs/2110.13117 ; Belyakov, Bernardinelli & Brown 2022, Limits on the Detection of Planet Nine in DES (AJ 163, 216): https://arxiv.org/abs/2203.07642
- Brown, Holman & Batygin 2024, A Pan-STARRS1 Search for Planet Nine: https://arxiv.org/abs/2401.17977
- Batygin, Morbidelli, Brown & Nesvorny 2024, Low-Inclination Neptune-Crossing TNOs: https://arxiv.org/abs/2404.11594
- Siraj, Chyba & Tremaine 2025, Orbit of a Possible Planet X (ApJ 978, 139): https://arxiv.org/abs/2410.18170
- Siraj, Chyba & Tremaine 2025, Measuring the Mean Plane of the Distant Kuiper Belt (MNRAS): https://arxiv.org/abs/2508.14156 ; Siraj, Chyba & Tremaine 2026, Measuring Apsidal Clustering: https://arxiv.org/abs/2604.25990
- Cheng, Li & Yang 2025, Discovery of a dwarf planet candidate: 2017 OF201: https://arxiv.org/abs/2505.15806 ; Astronomy.com 2025, New sednoid "Ammonite": https://www.astronomy.com/science/new-sednoid-ammonite-discovery-deepens-planet-nine-mystery/
- Shankman et al. 2017, OSSOS VI: https://arxiv.org/abs/1706.05348 ; Napier et al. 2021, No Evidence for Orbital Clustering in the Extreme TNOs: https://arxiv.org/abs/2102.05601
- Fienga et al. 2016, Constraints from Cassini data: https://arxiv.org/abs/1602.06116 ; Fienga et al. 2020, New constraints with INPOP19a (A&A 640, A6): https://www.aanda.org/articles/aa/abs/2020/08/aa37919-20/aa37919-20.html
- Newswise 2026, Rubin's cosmic survey begins: https://www.newswise.com/articles/rubin-s-cosmic-survey-begins-pitt-researchers-have-been-ready-for-decades
- Holman et al. 2018, HelioLinC: https://arxiv.org/abs/1805.02638
- Holman, Payne & Pal 2019, A TESS Search for Distant Solar System Planets (RNAAS 3, 160): https://arxiv.org/abs/1910.06383 ; Payne, Holman & Pal 2019, A TESS Search for Distant Solar System Objects: Yield Estimates: https://arxiv.org/abs/1911.03676
- Rice & Laughlin 2020, Exploring Trans-Neptunian Space with TESS: https://arxiv.org/abs/2010.13791
- Luhman 2014, A Search for a Distant Companion to the Sun with WISE (ApJ 781, 4): https://pure.psu.edu/en/publications/a-search-for-a-distant-companion-to-the-sun-with-the-wide-field-i/
- Meisner et al. 2017, Searching for Planet Nine with Coadded WISE and NEOWISE-Reactivation Images: https://arxiv.org/abs/1611.00015 ; Meisner et al. 2018, A 3pi Search for Planet Nine at 3.4 micron with WISE and NEOWISE: https://arxiv.org/abs/1712.04950
- Rowan-Robinson 2022, A search for Planet 9 in the IRAS data: https://arxiv.org/abs/2111.03831
- Phan et al. 2025, A Search for Planet Nine with IRAS and AKARI Data (PASA 42, e064): https://arxiv.org/abs/2504.17288
- Chen et al. 2025, A Far-Infrared Search for Planet Nine Using AKARI All-Sky Survey: https://arxiv.org/abs/2506.12854
- Naess et al. 2021, The Atacama Cosmology Telescope: A search for Planet 9 (ApJ 923, 224): https://arxiv.org/abs/2104.10264 ; Socas-Navarro & Trujillo 2025, A targeted, parallax-based search for Planet Nine: https://arxiv.org/abs/2504.05473
- Fortney et al. 2016, The Hunt for Planet Nine: Atmosphere, Spectra, Evolution, and Detectability: https://arxiv.org/abs/1604.07424
- Linder & Mordasini 2016, Evolution and Magnitudes of Candidate Planet Nine: https://arxiv.org/abs/1602.07465
- Ginzburg, Sari & Loeb 2016, Blackbody Radiation from Isolated Neptunes (ApJ 822, L11): https://arxiv.org/abs/1603.02876 ; Cowan, Holder & Kaib 2016, Cosmologists in Search of Planet Nine: https://arxiv.org/abs/1602.05963
- Crill et al. 2025, The SPHEREx Sky Simulator (ApJS 281, 10): https://arxiv.org/abs/2505.24856
- Bock et al. 2025, The SPHEREx Satellite Mission (accepted, ApJ): https://arxiv.org/abs/2511.02985
- Deep-field depth as quoted in Bayesian Multi-line Intensity Mapping: https://arxiv.org/abs/2403.19740
- SPHEREx survey page: https://spherex.caltech.edu/page/survey ; IRSA SPHEREx Quick Release overview: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_qr.html
- Ivezic et al. 2022, Simulated SPHEREx spectra of asteroids (Icarus 371, 114696): https://resolver.caltech.edu/CaltechAUTHORS:20210927-225706495
- Lisse, Bauer & Kim 2024, Planetary Defense Use of the SPHEREx Solar System Object Catalog: https://arxiv.org/abs/2402.08705 ; Lisse et al. 2025, SPHEREx Pre-Perihelion Mapping of H2O, CO2 and CO in 3I/ATLAS: https://arxiv.org/abs/2512.07318
- Gagne et al. 2026, A SPHEREx Pipeline and Spectral Library for Ultracool Dwarfs: https://arxiv.org/abs/2604.22012 ; Emery et al. 2024, A Tale of 3 Dwarf Planets (JWST: Sedna, Gonggong, Quaoar): https://arxiv.org/abs/2309.15230
- JPL Horizons ephemeris service: https://ssd.jpl.nasa.gov/horizons/
