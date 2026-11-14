# Planet Nine mode: protocol

Written on 14 Nov 2026 and hashed into `validation/ledger.jsonl` before the search was run.

## Question
Do the SPHEREx fields PARALLAX already holds contain a body between 200 and 20,000 AU from the Sun?

## Method
1. Take every source that appears in exactly one visit's stacked image at S/N >= 5, is not next to a saturated
   star, and has no Gaia star within 5 arcseconds.
2. Two such sources from different visits form a pair if some distance r lets one bound body explain both: the
   jump must equal the parallax for r, give or take the fastest bound orbital motion at r and 6 arcseconds.
   Their brightness must agree within a factor of 2.5.
3. Three sources, one in each of three visits, form a candidate if one orbit (five numbers: position, distance,
   sky motion) fits them with reduced chi-square <= 4, is bound, and fits at least 9 times worse when the Earth
   is mirrored through the Sun.
4. Pairs alone are never candidates: with two visits any two sources in the right direction fit some orbit.

## What would count as a result
- A candidate: reported as an unconfirmed candidate, with its three positions, for others to check.
- No candidate: an upper limit, valid only for the area searched and the depth reached.

## Sensitivity
Synthetic planets (never real) at 500, 800, 1200 and 2000 AU and 150 to 1200 microjansky are added to the real
images of a blank field and searched for in the same way. The faintest one recovered sets the quoted limit.

## Known weaknesses, stated in advance
- The fields were chosen for other reasons and cover about 2 square degrees. The predicted Planet Nine band
  covers thousands.
- Stacked depth is about 100 microjansky. The predicted planet is about 7.
- Fields are 20 arcminutes wide, so a body closer than about 450 AU leaves the field between visits.

## Version 2 (14 Nov 2026, same day)
Version 1 was locked (ledger entry 3) and run. It found no candidate in the real fields. The synthetic test then
showed a fault: it recovered synthetic planets at 300 microjansky but missed brighter ones at the same distance.
Two causes, both in how a stacked image was turned into a position:
1. A stack's position was dated at the middle of the visit. The short-wavelength exposures that made the stack can
   be days from that date, and a body at 500 AU drifts by arcseconds a day.
2. The position error for bright sources was 0.5 arcseconds. A stack blurs a drifting body by more than that.

Changes: each stack position is dated at the mean time of its own exposures, the position error floor is
2 arcseconds, and chains that the hunt had already joined as slow movers are split back into single-visit points
(a body at 2000 AU moves less than 15 arcseconds a year and was being absorbed by that step). The acceptance
thresholds are unchanged. Version 2 was locked before it was run on the real fields. The change was driven by
synthetic planets only; version 1 had produced no real candidate to tune on.

## Version 3 (14 Nov 2026, same day)
Version 2 (ledger entry 4) dated each stack at the MEAN time of its exposures. The synthetic test failed again
at 500 and 800 AU, and the cause was one exposure taken 25 days after the rest of its visit: it is rejected from
the stack as an outlier but still dragged the mean date by five days. Version 3 uses the MEDIAN exposure time.
Nothing else changed. Under version 2 the real fields gave one triple; it is reported in the results whatever
version 3 says about it.

## Version 4 (14 Nov 2026, same day): a rule added AFTER seeing real candidates
Version 3 (ledger entry 5) found two triples in the real fields that pass every geometric test:
- R Draconis field: three sources of 26,000 to 42,000 microjansky, fitted distance about 3,400 AU.
- Luhman 16 field: three sources of 3,900 to 5,900 microjansky, fitted distance about 2,300 AU.

Neither can be a planet. In reflected sunlight a twin of Jupiter would be about 0.3 microjansky at 3,400 AU and
1.5 at 2,300 AU, so these are ten thousand to a hundred thousand times too bright. The R Draconis sources lie
about one arcminute from that saturated star, at the same place in the two same-season visits and a different
place in the opposite season. That is how an optical reflection behaves, because the spacecraft is turned round
every six months, and it happens to imitate parallax. The Luhman 16 field is in the plane of the Milky Way and is
crowded with faint stars.

Rule added: a triple more than 10 times brighter than a Jupiter twin at its fitted distance is rejected as "too
bright for a planet". This rule was written after looking at these two cases, so it is not a blind rule. Both
cases stay in the results with the reason. The synthetic test ignores this rule: it tests the geometry only.
