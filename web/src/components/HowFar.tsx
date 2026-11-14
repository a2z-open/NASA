import { useEffect, useMemo, useState } from 'react';

/** Distances from the Sun in AU (1 AU = Earth to Sun). Planet Nine is a prediction, not a measurement. */
const THINGS = [
  { id: 'pluto', name: 'Pluto', au: 35.9, say: 'jumps about 6 Moon-widths. Easy to see.' },
  { id: 'makemake', name: 'Makemake', au: 52.7, say: 'jumps about 4 Moon-widths. The one you just found.' },
  { id: 'sedna', name: 'Sedna', au: 82, say: 'jumps under 3 Moon-widths.' },
  { id: 'eris', name: 'Eris', au: 95.5, say: 'jumps just over 2 Moon-widths. We found it too.' },
  { id: 'nine', name: 'Planet Nine?', au: 500, say: 'would jump less than half a Moon. If it is real, it is also very faint. Nobody has found it yet.' },
  { id: 'star', name: 'Nearest star', au: 268770, say: 'jumps as much as a coin seen from 3 km away. That is why stars look still.' },
];

const jumpDeg = (au: number) => (2 / au) * (180 / Math.PI);   // Earth's step across its orbit is 2 AU

function fmtJump(deg: number) {
  if (deg >= 0.1) return { n: deg.toFixed(deg >= 1 ? 1 : 2), u: '°' };
  const as = deg * 3600;
  return { n: as.toFixed(1), u: '″' };
}

// background stars for the drawing: fixed, pseudo-random
const STARS = Array.from({ length: 70 }, (_, i) => {
  const r = (n: number) => { const x = Math.sin(i * 127.1 + n * 311.7) * 43758.5453; return x - Math.floor(x); };
  return { x: 10 + r(1) * 780, y: 38 + r(2) * 64, s: 0.6 + r(3) * 1.6, o: 0.35 + r(4) * 0.6 };
});

/** Close things jump more: Earth on opposite sides of the Sun sees a nearby object against different background stars. */
export function HowFar() {
  const [id, setId] = useState('makemake');
  const [k, setK] = useState(0);
  const t = THINGS.find(x => x.id === id)!;
  const deg = jumpDeg(t.au);
  const j = fmtJump(deg);

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setK(-1); return; }
    const iv = window.setInterval(() => setK(v => 1 - v), 650);
    return () => window.clearInterval(iv);
  }, []);

  // The drawing is squeezed to fit (square-root of the real jump); the numbers beside it are real.
  const g = useMemo(() => {
    const S = 380 * Math.sqrt(35 / t.au);
    const f = 1 + S / 300;
    const yO = 440 - 370 / f;
    return { yO, xJ: 250 + 150 * f, xR: 550 - 150 * f };
  }, [t.au]);
  const showJ = k !== 1, showR = k !== 0;

  return (
    <div className="card far2">
      <div className="far2__side">
        <div className="far2__pick" role="group" aria-label="Pick something to measure">
          {THINGS.map(x => <button key={x.id} type="button" aria-pressed={x.id === id} onClick={() => setId(x.id)}>{x.name}</button>)}
        </div>
        <p className="far2__big num" aria-live="polite">{j.n}<small>{j.u}</small></p>
        <p className="far2__say"><strong>{t.name.replace('?', '')}</strong> {t.say}</p>
        <p className="far2__note">
          {t.au < 1000 ? `${t.au.toFixed(0)} times farther from the Sun than Earth.` : '4.2 light-years away.'}
          {' '}Measure the jump and you know the distance. That's how PARALLAX measured Makemake at 52.7 AU and Eris at 95.5 AU. NASA's JPL agrees.
        </p>
      </div>
      <figure className="far2__fig">
        <svg viewBox="0 0 800 500" role="img" aria-label={`Diagram: Earth in January and in July, on opposite sides of the Sun, both looking at ${t.name}. Each sees it against a different patch of background stars.`}>
          {STARS.map((s, i) => <circle key={i} cx={s.x} cy={s.y} r={s.s} fill="#f5f5f7" opacity={s.o} />)}
          <text x="20" y="26" fill="#86868b" fontFamily="Barlow, sans-serif" fontWeight="600" fontSize="13" letterSpacing="2.4">FAR-AWAY STARS</text>
          <line x1="250" y1="440" x2={g.xJ} y2="70" stroke="#f5f5f7" strokeWidth="1.6" strokeDasharray="6 6" opacity={showJ ? 1 : 0.15} />
          <line x1="550" y1="440" x2={g.xR} y2="70" stroke="#f5f5f7" strokeWidth="1.6" opacity={showR ? 1 : 0.15} />
          <circle cx={g.xJ} cy="70" r="9" fill="none" stroke="#f5f5f7" strokeWidth="2" strokeDasharray="4 4" opacity={showJ ? 1 : 0.15} />
          <circle cx={g.xR} cy="70" r="9" fill="none" stroke="#f5f5f7" strokeWidth="2.5" opacity={showR ? 1 : 0.15} />
          {Math.abs(g.xJ - g.xR) > 40 && (
            <g>
              <line x1={Math.min(g.xJ, g.xR) + 14} y1="112" x2={Math.max(g.xJ, g.xR) - 14} y2="112" stroke="#a1a1a6" strokeWidth="1.2" markerStart="url(#ah)" markerEnd="url(#ah)" />
              <text x={(g.xJ + g.xR) / 2} y="134" fill="#f5f5f7" textAnchor="middle" fontFamily="Barlow, sans-serif" fontWeight="600" fontSize="13" letterSpacing="2.4">THE JUMP</text>
            </g>
          )}
          <defs>
            <marker id="ah" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#a1a1a6" /></marker>
          </defs>
          <circle cx="400" cy={g.yO} r="7" fill="#f5f5f7" />
          <text x="414" y={g.yO + 5} fill="#f5f5f7" fontFamily="-apple-system, Inter, sans-serif" fontSize="16" fontWeight="500">{t.name}</text>
          <ellipse cx="400" cy="440" rx="150" ry="30" fill="none" stroke="rgba(245,245,247,0.22)" strokeWidth="1.2" strokeDasharray="3 6" />
          <circle cx="400" cy="440" r="10" fill="#f5f5f7" />
          <circle cx="250" cy="440" r="7" fill="#000" stroke="#f5f5f7" strokeWidth="2" strokeDasharray="3 3" />
          <circle cx="550" cy="440" r="7" fill="#f5f5f7" />
          <text x="250" y="482" fill="#a1a1a6" textAnchor="middle" fontFamily="Barlow, sans-serif" fontWeight="600" fontSize="13" letterSpacing="2">EARTH · JAN</text>
          <text x="400" y="482" fill="#86868b" textAnchor="middle" fontFamily="Barlow, sans-serif" fontWeight="600" fontSize="13" letterSpacing="2">SUN</text>
          <text x="550" y="482" fill="#f5f5f7" textAnchor="middle" fontFamily="Barlow, sans-serif" fontWeight="600" fontSize="13" letterSpacing="2">EARTH · JUL</text>
        </svg>
        <figcaption className="far2__cap eyebrow-x" style={{ fontSize: 11 }}><span>Not to scale</span><span>Numbers are real</span></figcaption>
      </figure>
    </div>
  );
}
