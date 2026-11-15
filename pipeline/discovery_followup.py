"""Find public SPHEREx exposure metadata near frozen asteroid predictions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import math
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from . import spherex

RADIUS_DEG = 0.05
TIME_MARGIN_DAYS = 30 / 1440


def predicted_fields(candidates: list[dict]) -> list[dict]:
    """Choose at most one forecast per night from the first ranked candidate with a holdout."""
    for candidate in candidates:
        fields = {}
        for row in sorted(candidate['observations'], key=lambda item: -item['mjd_utc']):
            if row['phase'] != 'test' or 'predicted_ra_deg' not in row or 'predicted_dec_deg' not in row:
                continue
            ra, dec = row['predicted_ra_deg'], row['predicted_dec_deg']
            if not (math.isfinite(ra) and -90 <= dec <= 90):
                continue
            fields.setdefault(row['night'], {'candidate_id': candidate['id'], 'night': row['night'],
                                            'mjd_utc': row['mjd_utc'], 'ra': ra % 360, 'dec': dec,
                                            'station': row['station'], 'sigma_major_arcsec': row.get('sigma_major_arcsec')})
        if fields:
            return list(fields.values())[:2]
    return []


def query_field(field: dict) -> dict:
    first = field['mjd_utc'] - TIME_MARGIN_DAYS
    last = field['mjd_utc'] + TIME_MARGIN_DAYS

    def query(collection):
        params = {'COLLECTION': collection, 'POS': f"CIRCLE {field['ra']:.7f} {field['dec']:.7f} {RADIUS_DEG}",
                  'TIME': f'{first:.8f} {last:.8f}', 'MAXREC': '100', 'RESPONSEFORMAT': 'VOTABLE'}
        receipt = {'collection': collection, 'params': params, 'endpoint': spherex.SIA_URL}
        try:
            response = spherex._get(spherex.SIA_URL, params=params, timeout=12, retries=2)
            receipt.update(url=response.url, sha256=sha256(response.content).hexdigest(),
                           retrieved_utc=datetime.now(timezone.utc).isoformat())
            query_status = {info.get('value') for info in ET.fromstring(response.content).iterfind('.//{*}INFO')
                            if info.get('name') == 'QUERY_STATUS'}
            if 'ERROR' in query_status or not query_status & {'OK', 'OVERFLOW'}:
                raise ValueError('Unsuccessful SIA query')
            products = []
            for product in spherex.parse_sia(response.content, collection):
                link = urlsplit(product.access_url)
                if (link.scheme == 'https' and link.netloc == spherex.IRSA_HOST
                        and product.t_min <= last and product.t_max >= first):
                    products.append(product)
            return receipt | {'status': 'truncated' if 'OVERFLOW' in query_status else 'complete'}, products
        except (spherex.ArchiveUnavailable, ET.ParseError, ValueError):
            return receipt | {'status': 'unavailable'}, []

    with ThreadPoolExecutor(max_workers=len(spherex.COLLECTIONS)) as executor:
        receipts, lists = zip(*executor.map(query, spherex.COLLECTIONS), strict=True)
    products = spherex.dedupe([product for entries in lists for product in entries])
    products.sort(key=lambda product: abs(product.t_mid - field['mjd_utc']))
    status = 'found' if products else ('no_results' if all(r['status'] == 'complete' for r in receipts) else 'incomplete')
    return {'status': status, 'products': [product.to_dict() for product in products[:12]],
            'products_found': len(products), 'receipts': list(receipts)}


def run_followup(fields: list[dict], first: int, report=lambda _: None) -> dict:
    checks = []
    if fields:
        for index in [first, *(i for i in range(len(fields)) if i != first)]:
            field = fields[index]
            report(f"Querying SPHEREx for the {field['night']} UTC prediction")
            check = query_field(field)
            checks.append(check | {'field': field})
            if check['status'] == 'found':
                status = 'found'
                break
        else:
            status = 'incomplete' if any(check['status'] == 'incomplete' for check in checks) else 'no_results'
    else:
        status = 'no_predictions'
    return {'status': status, 'checks': checks, 'radius_arcmin': RADIUS_DEG * 60,
            'margin_minutes': TIME_MARGIN_DAYS * 1440}
