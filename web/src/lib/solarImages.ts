interface SolarImage {
  file: string;
  caption: string;
  source: string;
}

// Keyed by the Horizons target ID so an unrelated name match cannot select an image.
export const SOLAR_IMAGES: Readonly<Record<string, SolarImage | undefined>> = {
  '10': { file: 'sun', caption: 'NASA Solar Dynamics Observatory · 10 Sep 2025', source: 'https://science.nasa.gov/photojournal/image-of-sun-from-nasas-solar-dynamics-observatory/' },
  '301': { file: 'moon', caption: 'Galileo · enhanced color · 7 Dec 1992', source: 'https://science.nasa.gov/photojournal/earths-moon/' },
  '199': { file: 'mercury', caption: 'MESSENGER · 14 Jan 2008', source: 'https://science.nasa.gov/photojournal/messengers-first-look-at-mercurys-previously-unseen-side/' },
  '299': { file: 'venus', caption: 'Galileo · colorized violet-light image · 14 Feb 1990', source: 'https://science.nasa.gov/photojournal/venus-cloud-patterns-colorized-and-filtered/' },
  '499': { file: 'mars', caption: 'Viking Orbiter 1 · image mosaic · 1970s', source: 'https://science.nasa.gov/photojournal/global-color-views-of-mars/' },
  '599': { file: 'jupiter', caption: 'Cassini · color mosaic · 29 Dec 2000', source: 'https://science.nasa.gov/photojournal/cassini-jupiter-portrait/' },
  '699': { file: 'saturn', caption: 'Cassini · natural-color mosaic · 2008', source: 'https://science.nasa.gov/resource/saturn-four-years-on/' },
  '799': { file: 'uranus', caption: 'Voyager 2 · Jan 1986', source: 'https://science.nasa.gov/photojournal/uranus-as-seen-by-nasas-voyager-2/' },
  '899': { file: 'neptune', caption: 'Voyager 2 · enhanced color · Aug 1989', source: 'https://science.nasa.gov/image-detail/amf-pia01492/' },
  '999': { file: 'pluto', caption: 'New Horizons · enhanced color · 14 Jul 2015', source: 'https://science.nasa.gov/photojournal/the-rich-color-variations-of-pluto/' },
  '1;': { file: 'ceres', caption: 'Dawn · enhanced color · 29 Apr 2017', source: 'https://science.nasa.gov/resource/enhanced-color-view-of-ceres-at-opposition/' },
  '4;': { file: 'vesta', caption: 'Dawn · 24 Jul 2011', source: 'https://science.nasa.gov/resource/full-frame-image-of-vesta/' },
  '101955;': { file: 'bennu', caption: 'OSIRIS-REx · image mosaic · 2 Dec 2018', source: 'https://science.nasa.gov/resource/bennu-mosaic/' },
  '486958;': { file: 'arrokoth', caption: 'New Horizons · 1 Jan 2019', source: 'https://science.nasa.gov/resource/first-images-of-arrokoth-2014-mu69/' },
};
