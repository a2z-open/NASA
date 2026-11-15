// The wavelengths and plane indices come from the IRSA SPHEREx DR1 cube properties.
const WAVES = [0.753, 0.771, 0.790, 0.809, 0.828, 0.848, 0.868, 0.889, 0.910, 0.932, 0.955, 0.978, 1.001, 1.025, 1.050, 1.075, 1.102, 1.113, 1.139, 1.167, 1.195, 1.224, 1.254, 1.284, 1.315, 1.346, 1.378, 1.412, 1.446, 1.481, 1.517, 1.554, 1.592, 1.631, 1.656, 1.695, 1.735, 1.775, 1.818, 1.861, 1.905, 1.949, 1.995, 2.041, 2.089, 2.139, 2.189, 2.240, 2.292, 2.345, 2.399, 2.445, 2.506, 2.575, 2.646, 2.719, 2.794, 2.871, 2.951, 3.033, 3.118, 3.204, 3.293, 3.383, 3.476, 3.570, 3.667, 3.768, 3.833, 3.867, 3.901, 3.935, 3.970, 4.005, 4.040, 4.076, 4.112, 4.148, 4.184, 4.220, 4.257, 4.294, 4.331, 4.368, 4.405, 4.435, 4.467, 4.500, 4.533, 4.566, 4.600, 4.635, 4.669, 4.704, 4.739, 4.773, 4.808, 4.843, 4.879, 4.915, 4.951, 4.988];

// IRSA publishes PNG planes from 1 through 101, with no PNG tiles for the two dichroic planes.
const UNAVAILABLE = new Set([0, 50, 51]);
const MIN_FREQUENCY = 299_792_458 / 5.009e-6;
const MAX_FREQUENCY = 299_792_458 / 0.743e-6;
const TILE_FREQUENCY_STEP = (MAX_FREQUENCY - MIN_FREQUENCY) / WAVES.length;

export const SPHEREX_MAP_BANDS = WAVES.flatMap((wavelength, plane) =>
  UNAVAILABLE.has(plane) ? [] : [{
    plane,
    wavelength,
    // Aladin Lite 3.8 indexes tiles in uniform frequency bins. Address the tile's bin center.
    // Display the physical wavelength from IRSA's lookup table, which is a different scale.
    tileFrequencyHz: MIN_FREQUENCY + (plane + 0.5) * TILE_FREQUENCY_STEP,
  }],
);
