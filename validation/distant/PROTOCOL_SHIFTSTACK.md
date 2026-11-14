# Shift-and-stack: protocol

Written on 14 Nov 2026 and hashed into `validation/ledger.jsonl` with `pipeline/shiftstack.py` and
`validation/shiftstack_run.py` before the method was run on real data.

## Why
Eris was missed by the distant-world search because it never reaches the detection limit in one exposure. Measured
afterwards at JPL's position, it is at about S/N 3 per exposure. That measurement was made before this method was
written, and is disclosed here: it told us shift-and-stack should work, not where Eris is.

## Method (constants in `pipeline/shiftstack.py`)
For each visit: resample every exposure (0.75 to 2.4 µm) onto one grid of 6.15″ pixels, subtract the median of the
visit's exposures (the static sky), mask star cores, matched-filter, then add the exposures along every trial motion up
to 12″ a day in steps of one pixel across the visit. Motions that move a body less than 1.5 pixels across the visit
are not tried (they are indistinguishable from a star). Peaks at 7σ or more, after renormalising each trial map,
become candidates. Candidates from different visits are joined by one bound orbit (reduced χ² ≤ 4) that fits at least
nine times worse with the Earth mirrored through the Sun.

## Pass rule (fixed now)
- The accepted object lies within 15″ (median) of JPL's track.
- Its fitted distance is within 10 % of JPL's.
- No other object is accepted in the same fields.

## Scope
The fields were chosen with the ephemeris, as for the first test. This is a test of depth, not a discovery search.

## Version 2 (14 Nov 2026, same day, before any scoring)
Version 1 (method locked as ledger entry 11, blind result entry 12) found candidates of 7 to 13σ in every visit but linked
none. The best cross-visit pairs fitted distances of 92 to 103 AU with reduced χ² of 4.0 to 4.6, just above the limit, and
the six-number orbit came out unbound. Two causes, found without opening the ephemeris:
1. positions and motions were only known to the nearest pixel and to the trial step;
2. two short arcs cannot measure the speed towards or away from the Sun, and leaving it free let the fit run unbound.

Changes: each peak is refined below the pixel and the trial step (fractional shifts and a parabola), its position error
is set to 2.5″ (3.5″ at the ends of the visit), and visits are linked with the five-number orbit (radial speed held at
zero), as the Planet Nine linker already does. Thresholds and the pass rule are unchanged. Version 1's result stays on
record as a miss. Version 2 was locked before it was run.

## Version 3 (14 Nov 2026, same day, before any scoring)
Version 2 (method entry 13, blind result entry 14) again linked nothing. The residuals were small at each visit's centre
and large (6 to 16″) at its ends, always in a pattern that a straight line cannot follow. Near 90 degrees from the Sun a
world at about 100 AU moves on a curved path within a two-week visit (the Earth's motion bends it by up to about 15″ at
the ends of a visit), so the straight-line motion found by shift-and-stack is right on average but wrong at the ends.

Change: visits are linked by each candidate's centre position only, one candidate from each of three visits, with the
five-number orbit, reduced χ² ≤ 4, bound, and the mirrored-Earth test. Two-visit links are no longer made by this search.
Before writing this version we checked, without the ephemeris, that some three-visit combination of the existing
candidates fits; that check is the reason for the change and is disclosed here. The thresholds and the pass rule are
unchanged, and versions 1 and 2 stay on record as misses.
