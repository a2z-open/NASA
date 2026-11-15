"""Planet Nine deep stack: the motion grid, the controls, the stack itself and the fixed-sky template (synthetic data only)."""

import numpy as np

from validation import p9_deepstack as P

MJD = 61040.0 + np.linspace(0, 20, 30)
TREF = float(MJD.mean())


def test_trial_grid_is_fine_enough():
    trials, reach = P._trials(MJD, TREF)
    ds = sorted({d for d, _ in trials})
    assert ds[0] >= P.D_MIN - 1 and ds[-1] <= P.D_MAX + 1
    for a, b in zip(ds[:-1], ds[1:]):                       # the farthest image moves by at most half a native pixel
        assert reach * abs(1 / a - 1 / b) <= 0.5 * P.PIX + 1e-6


def test_controls_are_impossible_motions():
    u, v = P._offsets(MJD, TREF, 300.0, 0.0, 'real')
    ur, vr = P._offsets(MJD, TREF, 300.0, 0.0, 'reversed')
    uo, vo = P._offsets(MJD, TREF, 300.0, 0.0, 'rotated')
    assert np.allclose(ur, -u) and np.allclose(vr, -v)
    assert np.allclose(uo, -v) and np.allclose(vo, u)
    assert np.max(np.hypot(u, v)) > 1.0                     # it really moves by more than a grid pixel over the visit


def test_stack_finds_a_planet_too_faint_for_one_image():
    rng = np.random.default_rng(3)
    n, N = 90, len(MJD)
    trials, _ = P._trials(MJD, TREF)
    d, r = trials[len(trials) // 2]
    u, v = P._offsets(MJD, TREF, d, r, 'real')
    yy, xx = np.mgrid[:n, :n]
    R = rng.normal(0, 1, (N, n, n))
    w = np.ones((N, n, n))
    for i in range(N):                                       # peak S/N 1.2 in each image: invisible in any one of them
        R[i] += 1.2 * np.exp(-((xx - n // 2 - u[i]) ** 2 + (yy - n // 2 - v[i]) ** 2) / (2 * 0.8 ** 2))
    res = {m: P._stack_all(R, w, MJD, TREF, trials, m)[:2] for m in ('real', 'reversed', 'rotated')}
    best = res['real'][0]
    yb, xb = np.unravel_index(np.argmax(np.nan_to_num(best, nan=-np.inf)), best.shape)
    assert abs(yb - n // 2) <= 1 and abs(xb - n // 2) <= 1
    assert best[yb, xb] > 5
    near = [p for p in P._marked(res, 'real') if abs(p['y'] - n // 2) <= 1 and abs(p['x'] - n // 2) <= 1]
    assert near and near[0]['margin'] >= P.MOTION_MARGIN    # it beats both impossible motions


def test_template_from_other_visits_removes_a_star_and_keeps_a_planet():
    rng = np.random.default_rng(5)
    N, n = 40, 40
    target = np.zeros(N, bool)
    target[:15] = True
    L = np.broadcast_to(rng.uniform(0.75, 1.6, N)[:, None, None], (N, n, n)).copy()
    S = np.full((N, n, n), 10.0)
    F = rng.normal(0, 10, (N, n, n))
    F[:, 10, 10] += 300 * (1 + 0.5 * (L[:, 10, 10] - 1.1))   # a star with a sloping spectrum, in every image
    F[target, 30, 30] += 30                                   # a planet, there only during the searched visit
    R, w, _, _ = P._clean(F, S, L, target)
    assert abs(np.mean(R[:, 10, 10])) < 10
    assert np.mean(R[:, 30, 30]) > 20
