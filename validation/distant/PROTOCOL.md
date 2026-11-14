# Distant-world search: protocol and pass rule

Written on 14 Nov 2026, before any distant body was scored. The thresholds are constants in
`pipeline/distant.py` (`thresholds()`), and the pass rule is `PASS` in `validation/distant_run.py`.

## What is tested
Can the search find a known distant body in real SPHEREx images and measure its distance, without being told
where the body is or how it moves?

## What the ephemeris is used for
1. Choosing which patches of sky to download (`validation/distant_fields.py`). A body at 50 AU moves about
   2 degrees between visits, so no fixed patch contains it twice. Each patch is 16 arcminutes wide and is
   centred where JPL Horizons puts the body at the middle of a two-day bin.
2. Scoring, after the blind result is locked.

The detection, orphan, tracklet and orbit code never reads an ephemeris. The patches are chosen because a
known body is there, so this measures whether the search works. It is not a discovery test.

## Order of steps
1. `detect`: every exposure, matched filter at S/N >= 5, registered to Gaia DR3. A detection within 1.3 pixels
   of a Gaia DR3 or CatWISE2020 source is "explained" and dropped. What is left are orphans.
2. `link`: orphans in one visit are joined along a straight sky track (at least 4 exposures). Tracklets from
   different visits are joined by one orbit under the Sun's gravity. The orbit must be bound, have reduced
   chi-square <= 4, and fit at least 9 times worse when the Earth is mirrored through the Sun.
3. The blind result (`blind.json`) is hashed into `validation/ledger.jsonl`.
4. `score`: refuses to run if `blind.json` differs from its lock. Then it opens the ephemeris.

## Pass rule (fixed in advance)
- At least 90 % of the linked detections lie within 12 arcseconds (2 pixels) of the JPL position.
- The fitted heliocentric distance is within 5 % of the JPL distance.
- No other object is accepted in the same fields (a false link would count against the search).

## What a failure looks like
Not recovered, a distance off by more than 5 %, or a second accepted object. Failures are reported as they are.
