"""Gaia DR3 lookups fall back to NASA's MAST mirror when ESA's archive does not answer."""

import io

import numpy as np
import pytest
from astropy.io.votable import from_table, writeto
from astropy.table import Table

import pipeline.measure as m

COLS = ['source_id', 'ra', 'dec', 'pmra', 'pmdec', 'parallax', 'pmra_error', 'pmdec_error', 'parallax_error',
        'phot_g_mean_mag', 'bp_rp', 'ruwe', 'ref_epoch']


def _votable(rows):
    t = Table(rows=rows, names=COLS, dtype=[np.int64] + [np.float64] * (len(COLS) - 1))
    buf = io.BytesIO()
    writeto(from_table(t), buf)
    return buf.getvalue()


class _Resp:
    def __init__(self, text='', content=b'', status=200):
        self.text, self.content, self.status_code = text, content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError('http error')


class _Http:
    """ESA is down; MAST answers with the rows given."""

    def __init__(self, mast_rows, esa_down=True):
        self.mast_rows, self.esa_down, self.calls = mast_rows, esa_down, []

    def post(self, url, data=None, timeout=None):
        self.calls.append((url, data['QUERY']))
        if url == m.GAIA_TAP:
            if self.esa_down:
                raise ConnectionError('ESA unreachable')
            return _Resp(text='source_id,ra,dec\n1,10.0,20.0\n')
        return _Resp(content=_votable(self.mast_rows))


def test_esa_answer_is_used_when_esa_is_up():
    http = _Http([], esa_down=False)
    rows = m.gaia_query('SELECT source_id, ra, dec FROM gaiadr3.gaia_source', http=http)
    assert rows == [{'source_id': '1', 'ra': '10.0', 'dec': '20.0'}]
    assert [u for u, _ in http.calls] == [m.GAIA_TAP]


def test_mast_answers_when_esa_is_down():
    row = (6412596012146801152, 330.8, -56.79, 3966.7, -2536.2, 270.66, 0.02, 0.02, 0.03, 15.0, 3.1, 1.0, 2016.0)
    http = _Http([row])
    rows = m.gaia_query('SELECT * FROM gaiadr3.gaia_source WHERE x', http=http)
    assert [u for u, _ in http.calls] == [m.GAIA_TAP, m.GAIA_TAP_MAST]
    assert 'dbo.gaia_source' in http.calls[1][1] and 'gaiadr3.' not in http.calls[1][1]
    assert rows[0]['source_id'] == '6412596012146801152'      # kept as text, like ESA's CSV
    assert rows[0]['parallax'] == pytest.approx(270.66)


def test_both_down_raises_a_clear_error():
    class Dead:
        def post(self, url, data=None, timeout=None):
            raise ConnectionError('down')
    with pytest.raises(ConnectionError, match='ESA.*MAST'):
        m.gaia_query('SELECT 1 FROM gaiadr3.gaia_source', http=Dead())


def test_gaia_field_cuts_the_padded_mast_cone_exactly(monkeypatch):
    # one star just inside a 0.1 deg circle, one just outside (MAST is asked for a wider cone)
    inside = (1, 10.0, 20.0 + 0.0995, 0, 0, 1, 0.1, 0.1, 0.1, 15.0, 1.0, 1.0, 2016.0)
    outside = (2, 10.0, 20.0 + 0.1005, 0, 0, 1, 0.1, 0.1, 0.1, 15.0, 1.0, 1.0, 2016.0)
    http = _Http([inside, outside])
    real_query = m.gaia_query
    monkeypatch.setattr(m, 'gaia_query', lambda adql, **kw: real_query(adql, **{**kw, 'http': http}))
    rows = m.gaia_field(10.0, 20.0, 0.1)
    assert [r['source_id'] for r in rows] == ['1']
    assert 'CIRCLE(10.0000000, 20.0000000, 0.11056)' in http.calls[1][1]   # 0.1 * 1.1 + 2"
    assert rows[0]['g'] == 15.0 and rows[0]['ref_epoch'] == 2016.0
