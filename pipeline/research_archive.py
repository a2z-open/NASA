"""Bounded, reproducible optical archive reconnaissance for the Aiges agent."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import math
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .discovery import chunk_region

ARCHIVE = 'https://astroarchive.noirlab.edu'
SEARCH_URL = ARCHIVE + '/api/adv_search/find/'
ROW_LIMIT = 600
MAX_OPTICAL_DAYS = 732
FIELDS = ['md5sum', 'archive_filename', 'dateobs_min', 'ra_center', 'dec_center',
          'release_date', 'exposure', 'ifilter', 'proposal', 'seeing', 'PHOTDPTH', 'EXPNUM']


class OpticalSurvey(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chunks: list[str] = Field(min_length=1, max_length=2)
    start: date
    end: date

    @model_validator(mode='after')
    def scope(self):
        if len(set(self.chunks)) != len(self.chunks):
            raise ValueError('Choose different chunks.')
        for chunk in self.chunks:
            chunk_region(chunk)
        if not 1 <= (self.end - self.start).days < MAX_OPTICAL_DAYS:
            raise ValueError('Give a range of 2 to 732 UTC days for the optical archive.')
        if self.start < date(2012, 9, 1) or self.end > datetime.now(timezone.utc).date():
            raise ValueError('Use past observing dates from September 2012 onward for DECam.')
        return self


def exposure(row: dict, scope: OpticalSurvey, chunk: str) -> dict | None:
    try:
        stamp = datetime.fromisoformat(row['dateobs_min'].replace('Z', '+00:00'))
        stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
        released = date.fromisoformat(row['release_date'][:10])
        digest = row['md5sum']
        expnum = int(row['EXPNUM'])
        ra, dec, seconds = (float(row[key]) for key in ('ra_center', 'dec_center', 'exposure'))
        depth, seeing = (float(row[key]) for key in ('PHOTDPTH', 'seeing'))
        band = row['ifilter'].split()[0]
        region = chunk_region(chunk)
        if (not scope.start <= stamp.date() <= scope.end or released > datetime.now(timezone.utc).date()
                or not re.fullmatch(r'[a-fA-F0-9]{32}', digest) or expnum <= 0
                or not region.ra_min <= ra < region.ra_max or not region.dec_min <= dec <= region.dec_max
                or not all(map(math.isfinite, (ra, dec, seconds, depth, seeing)))
                or seconds < 50 or not 21.4 <= depth <= 32 or not 0.45 <= seeing <= 2
                or band not in {'g', 'r', 'i', 'z', 'VR'}):
            return None
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None
    return {'exposure_id': expnum, 'product': str(row.get('archive_filename', ''))[:200],
            'utc': stamp.isoformat(), 'night': stamp.date().isoformat(), 'chunk': chunk,
            'ra': ra, 'dec': dec, 'seconds': seconds, 'band': band, 'depth_mag': depth,
            'seeing_arcsec': seeing, 'proposal': str(row.get('proposal', ''))[:80], 'md5': digest,
            'url': f'{ARCHIVE}/api/retrieve/{digest}/'}


def query_chunk(scope: OpticalSurvey, chunk: str) -> tuple[dict, list[dict]]:
    region = chunk_region(chunk)
    query = {'outfields': FIELDS, 'search': [
        ['caldat', (scope.start - timedelta(days=1)).isoformat(), (scope.end + timedelta(days=1)).isoformat()],
        ['ra_center', region.ra_min, region.ra_max], ['dec_center', region.dec_min, region.dec_max],
        ['instrument', 'decam'], ['proc_type', 'instcal'], ['prod_type', 'image'], ['exposure', 50, 3600],
    ]}
    receipt = {'chunk': chunk, 'endpoint': SEARCH_URL, 'query': query, 'limit': ROW_LIMIT,
               'retrieved_utc': datetime.now(timezone.utc).isoformat()}
    try:
        response = httpx.post(SEARCH_URL, json=query, params={'rectype': 'file', 'limit': ROW_LIMIT}, timeout=22)
        receipt.update(http_status=response.status_code, response_sha256=sha256(response.content).hexdigest())
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
            raise ValueError('Unexpected NOIRLab result shape')
        # NOIRLab puts query metadata before the file rows.
        if any('archive_filename' not in row or 'md5sum' not in row for row in rows[1:]):
            raise ValueError('NOIRLab did not return file-metadata rows')
        records = rows[1:]
        exposures = [item for row in records if (item := exposure(row, scope, chunk))]
        capped = len(records) >= ROW_LIMIT or rows[0].get('LIMIT') is True or rows[0].get('OVERFLOW') is True
        return receipt | {'status': 'truncated' if capped else 'complete', 'rows': len(records)}, exposures
    except httpx.HTTPError as error:
        return receipt | {'status': 'unavailable', 'reason': type(error).__name__}, []
    except (TypeError, ValueError):
        return receipt | {'status': 'unavailable', 'reason': 'Unrecognized metadata response'}, []


def survey(scope: OpticalSurvey, report) -> dict:
    report('Checking public DECam records at NSF NOIRLab')
    with ThreadPoolExecutor(max_workers=len(scope.chunks)) as pool:
        checks = list(pool.map(lambda chunk: query_chunk(scope, chunk), scope.chunks))
    receipts = [receipt for receipt, _ in checks]
    unique = {row['exposure_id']: row for _, rows in checks for row in rows}
    # Nearby pointing centers in the same band nominate a field. They do not prove CCD overlap.
    report('Ranking pointing groups by observing nights and reported depth')
    fields = {}
    for row in unique.values():
        area = (row['chunk'], row['band'], round(row['ra'] * 2), round(row['dec'] * 2))
        nights = fields.setdefault(area, {})
        existing = nights.get(row['night'])
        if existing is None or existing['depth_mag'] < row['depth_mag']:
            nights[row['night']] = row
    ranked = [sorted(nights.values(), key=lambda row: row['utc']) for nights in fields.values()]
    ranked.sort(key=lambda group: (len(group) >= 2, (date.fromisoformat(group[-1]['night']) -
                 date.fromisoformat(group[0]['night'])).days >= 120, len(group),
                 min(row['depth_mag'] for row in group)), reverse=True)
    groups = [{'chunk': rows[0]['chunk'], 'band': rows[0]['band'], 'nights': len(rows),
               'first_night': rows[0]['night'], 'last_night': rows[-1]['night'],
               'depth_floor_mag': min(row['depth_mag'] for row in rows), 'exposures': rows}
              for rows in ranked[:5]]
    return {
        'kind': 'optical', 'request': scope.model_dump(mode='json'), 'receipts': receipts,
        'eligible_exposures': len(unique), 'repeat_groups': sum(len(group) >= 2 for group in ranked),
        'groups': groups, 'archive_url': ARCHIVE, 'exposures': sorted(unique.values(), key=lambda row: row['utc']),
        'limits': [
            'This bounded file-metadata survey ranks similar pointing centers and does not verify CCD overlap, gaps, masks, or crowding.',
            'Reported depth is an archive metadata estimate. Pixel detection, injected-object recovery, and false-alert rates have not been measured.',
            'No object detection, orbit, or exclusion follows from a file match or empty query.',
        ],
    }


def optical_reply(packet: dict) -> str:
    requested = packet['request']
    scope = f"{' and '.join(requested['chunks'])} from {requested['start']} to {requested['end']} UTC"
    if all(r['status'] == 'unavailable' for r in packet['receipts']):
        return f'NOIRLab did not return usable metadata for {scope}. I can’t establish DECam coverage from this run.'
    count, repeat = packet['eligible_exposures'], packet['repeat_groups']
    answer = f'I found {count} eligible DECam exposures and {repeat} pointing groups with more than one observing night in {scope}.'
    if any(r['status'] != 'complete' for r in packet['receipts']):
        answer += ' Some queries were capped or unavailable, so coverage is incomplete.'
    return answer + ' This is a file inventory. The next test is to verify CCD coverage and measure recovery of planted sources before searching for a planet.'
