import type { ReactNode } from 'react';

const GLOSSARY: Record<string, string> = {
  'proper motion': 'How fast a star drifts across the sky, in milliarcseconds per year (mas/yr). Nearby stars move fastest.',
  'parallax': 'The small yearly wobble of a nearby star caused by Earth orbiting the Sun. Bigger parallax = closer. 1000 mas ↔ 1 parsec.',
  'reduced chi-square': 'How well a model fits, relative to the measurement errors. About 1 means the model explains the data within its uncertainties.',
  'wavelength-matched': 'SPHEREx sees each patch of sky through a filter whose wavelength changes across the detector. Two exposures are only directly comparable when they sample the same wavelength.',
  'reprojected': 'For display, every exposure is resampled onto one common north-up grid. Measurements use the original (native) pixels.',
  'held-out': 'Data the model never saw while it was being fitted. Predicting it is a real test, not a fit.',
  'ePSF': 'Effective point-spread function: the shape a point of light makes on the detector, supplied with each SPHEREx image.',
  'd²': 'Mahalanobis distance squared: how far the measurement fell from the prediction, in units of the combined uncertainty. Below 11.83 counts as within the 99.73% region.',
};

export function Term({ t, children }: { t: string; children: ReactNode }) {
  const text = GLOSSARY[t];
  if (!text) return <>{children}</>;
  return (
    <span className="term" tabIndex={0} aria-describedby={undefined}>
      {children}
      <span className="term__tip" role="tooltip">{text}</span>
    </span>
  );
}
