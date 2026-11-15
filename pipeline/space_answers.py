"""Space questions, with plain-language explanations and NASA source lookups."""

from functools import lru_cache
from html import unescape
from html.parser import HTMLParser
import re
import time
from urllib.parse import urlsplit

import httpx


NASA_SCIENCE = 'https://science.nasa.gov'
NASA_SITES = (NASA_SCIENCE, 'https://www.nasa.gov')
USER_AGENT = 'PARALLAX/1.0 (https://github.com/a2z-open/NASA)'
QUESTION_OPENING = re.compile(
    r'^(?:(?:hi|hey|please|can you|could you)[, ]+)*'
    r'(?:what (?:is|are|was|were|about|can you tell me about|do we know about)|'
    r'tell me (?:about|everything about)|explain|define|research(?: about)?)\s+'
)
REFERENCE = re.compile(r'\b(?:it|its|they|them|that mission|that object)\b')
STOP_WORDS = set(
    'a an and are about at be can could did do does for from give had has have how i in is it its me of '
    'on please s tell than that the their them they this to was were what when where which '
    'who why will with would you'.split()
)

# Short explanations based on the linked NASA references.
SUMMARIES = (
    (('space', 'astronomy', 'outer space'), '/exoplanets/what-is-the-universe/', 'The universe',
     'Space contains the planets of our solar system, stars and clouds in the Milky Way, and other galaxies far beyond it. '
     'Astronomers learn about them by measuring light, tracking motion, and observing events such as stellar explosions. '
     'Ask me about an object, a mission, or a particular idea such as gravity or the Big Bang.'),
    (('black hole', 'black holes', 'event horizon'), '/universe/black-holes/', 'Black holes',
     'A black hole is a region where gravity traps anything that crosses a boundary called the event horizon, including light. '
     'Some form when massive stars collapse. We can detect black holes by watching nearby stars, hot gas, or the gravitational waves from mergers.'),
    (('star formation', 'how do stars form', 'how are stars born', 'stars', 'star'), '/universe/stars/', 'Stars',
     'Stars form when a dense part of a cold cloud of gas and dust collapses under gravity. The center heats up as it shrinks. '
     'A star enters its main sequence when hydrogen fusion in its core sustains its energy output.'),
    (('mars', 'why is mars red', 'why does mars look red'), '/mars/facts/', 'Mars facts',
     'Mars looks red because much of its surface dust contains iron oxides, minerals commonly called rust. '
     'Winds carry that dust around the planet, and storms can spread it high into the atmosphere.'),
    (('venus', 'why is venus so hot', 'why is venus hotter than mercury'), '/venus/facts/', 'Venus facts',
     'Venus is the second planet from the Sun. A dense carbon dioxide atmosphere traps enough heat to make its surface hotter than Mercury’s. '
     'Its clouds contain droplets of sulfuric acid.'),
    (('mercury', 'closest planet to the sun'), '/mercury/facts/', 'Mercury facts',
     'Mercury is the closest planet to the Sun and the smallest planet in our solar system. Its dayside can get very hot. '
     'Some craters near the poles stay in shadow and contain water ice.'),
    (('pluto', 'why is pluto a dwarf planet', 'why is pluto not a planet'), '/dwarf-planets/pluto/facts/', 'Pluto facts',
     'Pluto is a dwarf planet in the Kuiper Belt. It is round under its own gravity and orbits the Sun, but shares its orbital neighborhood with many other objects. '
     'New Horizons flew past it in 2015 and imaged mountains and plains made of ice.'),
    (("saturn's rings", 'saturn rings', "what are saturn's rings made of", 'why does saturn have rings'),
     '/mission/cassini/science/rings/', 'Saturn’s rings',
     'Saturn’s rings are mostly bits of water ice, from fine grains to large chunks. Each piece travels around Saturn in its own orbit. '
     'Cassini found that geysers on the moon Enceladus feed much of the faint E ring.'),
    (('exoplanet', 'exoplanets', 'how do telescopes find exoplanets', 'how do we find exoplanets'),
     '/exoplanets/', 'Exoplanets',
     'An exoplanet is a planet outside our solar system. A telescope can detect a transit when a planet crosses in front of its star and briefly dims it. '
     'Astronomers can also measure the star’s wobble caused by the planet’s gravity.'),
    (('eclipse', 'eclipses', 'solar eclipse', 'lunar eclipse', 'how do eclipses happen', 'why do eclipses happen'),
     '/moon/eclipses/', 'Eclipses and the Moon',
     'During a solar eclipse, the Moon passes between the Sun and Earth and casts a shadow on Earth. During a lunar eclipse, the Moon crosses Earth’s shadow. '
     'The Moon’s orbit is tilted, so the three objects usually pass out of alignment.'),
    (('moon phases', 'phases of the moon', 'why does the moon change shape'), '/moon/moon-phases/', 'Moon phases',
     'The Sun usually lights half the Moon. As the Moon orbits Earth, we see different fractions of that lit half. '
     'That changing viewing angle produces the cycle of phases.'),
    (('big bang', 'age of the universe', 'how old is the universe', 'universe'),
     '/exoplanets/what-is-the-universe/', 'The universe',
     'The universe has been expanding for about 13.8 billion years. The Big Bang model describes its evolution from an extremely hot, dense early state. '
     'Light left over from that early universe is visible today as the cosmic microwave background.'),
    (('cosmic microwave background', 'cmb'), '/mission/webb/big-bang-q-and-a/', 'Light from the early universe',
     'The cosmic microwave background is ancient light that began traveling freely when the universe cooled enough to become transparent, about 380,000 years after the Big Bang. '
     'Cosmic expansion has stretched that light into microwaves.'),
    (('spherex', 'what does spherex do'), '/mission/spherex/', 'SPHEREx mission',
     'SPHEREx is a NASA space telescope that surveys the whole sky at many infrared wavelengths. '
     'It measures how light varies with wavelength to study galaxies, the early universe, and ices in clouds where stars and planets form.'),
    (('webb', 'jwst', 'james webb space telescope', 'what does jwst do', 'what does webb do'),
     '/mission/webb/', 'James Webb Space Telescope',
     'The James Webb Space Telescope observes mostly infrared light. This helps it study distant galaxies, see into some dusty star-forming regions, '
     'and measure the wavelengths absorbed by gases in exoplanet atmospheres.'),
    (('hubble', 'hubble space telescope', 'when did hubble launch', 'when was hubble launched'),
     '/mission/hubble/', 'Hubble Space Telescope',
     'Hubble launched aboard Space Shuttle Discovery on April 24, 1990. It observes visible, ultraviolet, and near-infrared light from above Earth’s atmosphere.'),
    (('titan', 'titan atmosphere', 'does titan have an atmosphere', "what is titan's atmosphere made of"),
     '/saturn/moons/titan/facts/', 'Titan facts',
     'Titan, Saturn’s largest moon, has a thick atmosphere made mostly of nitrogen, with a smaller amount of methane. '
     'Methane forms clouds and rain and collects in lakes and seas on the surface.'),
    (('mimas',), '/saturn/moons/mimas/', 'Mimas',
     'Mimas is a small, mostly icy moon of Saturn. Its most striking feature is Herschel, an enormous impact crater that spans roughly a third of the moon’s diameter.'),
    (('galaxy', 'galaxies'), '/universe/galaxies/', 'Galaxies',
     'Galaxies are systems of stars, gas, dust, and dark matter held together by gravity. They come in spiral, elliptical, and irregular shapes. '
     'Our Sun is one of the stars in the Milky Way, a barred spiral galaxy.'),
    (('neutron star', 'neutron stars'), '/universe/stars/', 'Stars',
     'A neutron star is the collapsed core left behind by some massive stars after they explode. It compresses roughly the mass of a star into a sphere about the size of a city. '
     'Some emit beams that sweep past Earth as regular pulses. We call those pulsars.'),
)


class PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = False

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden = True
        elif tag in {'p', 'li', 'h2', 'h3', 'div', 'br'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.hidden = False
        elif tag in {'p', 'li', 'h2', 'h3', 'div'}:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def words(text: str) -> set[str]:
    return {w.rstrip('s') if len(w) > 4 else w
            for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in STOP_WORDS}


def clean_question(message: str, topic: str | None) -> str:
    query = QUESTION_OPENING.sub('', message.casefold().replace('’', "'"))
    query = re.sub(r'^(?:the|a|an)\s+', '', query)
    query = re.sub(r'[^\w\s.\'-]', ' ', query).strip(' .')
    if topic and REFERENCE.search(query):
        query = REFERENCE.sub(lambda match: f"{topic}'s" if match[0] == 'its' else topic, query)
    return ' '.join(query.split())[:120]


def nasa_article_excerpt(post: dict, keywords: set[str]) -> str | None:
    parser = PageText()
    parser.feed(post.get('excerpt', {}).get('rendered', '') + '\n' + post.get('content', {}).get('rendered', '')[:160_000])
    lines = [re.sub(r'\s+', ' ', line).strip() for line in ''.join(parser.parts).splitlines()]
    sentences = [sentence for line in lines for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', line)
                 if 8 <= len(sentence.split()) and (words(sentence) & keywords)]
    if not sentences:
        return None
    selected = max(sentences, key=lambda sentence: (len(words(sentence) & keywords), len(sentence.split()) <= 25))
    parts = selected.split()
    return selected if len(parts) <= 25 else ' '.join(parts[:25]).rstrip(',;:') + '…'


@lru_cache(maxsize=128)
def nasa_lookup(query: str, _time_slot: int) -> tuple[str, str, str] | None:
    keywords = words(query)
    if not keywords:
        return None
    with httpx.Client(timeout=4.0, headers={'User-Agent': USER_AGENT}) as client:
        for host in NASA_SITES:
            base = host + '/wp-json/wp/v2'
            response = client.get(base + '/search', params={
                'search': query, 'per_page': 20, '_fields': 'id,title,url,subtype',
            })
            if not response.is_success:
                continue
            results = response.json()

            def rank(item):
                title = unescape(item['title'])
                path = urlsplit(item['url']).path
                return (len(keywords & words(title)), '/mission/' in path, -len(title))

            candidates = [item for item in results
                          if urlsplit(item['url']).netloc == urlsplit(host).netloc
                          and urlsplit(item['url']).scheme == 'https'
                          and not urlsplit(item['url']).path.startswith(
                              ('/apod/', '/image-article/', '/photojournal/', '/3d-resources/', '/gallery/'))
                          and '/community/' not in item['url']
                          and re.fullmatch(r'[a-z][a-z0-9-]*', item['subtype'])
                          and type(item['id']) is int
                          and rank(item)[0] >= min(2, len(keywords))]
            for item in sorted(candidates, key=rank, reverse=True)[:2]:
                post = client.get(f"{base}/{item['subtype']}/{item['id']}", params={'_fields': 'excerpt,content'})
                if not post.is_success:
                    continue
                excerpt = nasa_article_excerpt(post.json(), keywords)
                if excerpt:
                    return excerpt, unescape(item['title']), item['url']
    return None


def space_answer(message: str, topic: str | None = None, *, search_nasa: bool = True) -> dict:
    query = clean_question(message, topic)
    for aliases, path, label, answer in SUMMARIES:
        if query in aliases:
            return {'reply': answer, 'space_topic': aliases[0],
                    'sources': [{'label': f'NASA · {label}', 'href': NASA_SCIENCE + path}]}
    if not search_nasa:
        return {}
    keywords = ' '.join(word for word in query.split() if word not in STOP_WORDS)
    try:
        result = nasa_lookup(keywords, int(time.time() // 900)) if keywords else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return {'reply': 'I couldn’t reach the NASA reference search. Try again shortly or ask about a specific planet, star, or mission.'}
    if result is None:
        return {'reply': 'I couldn’t find a NASA source that answers that. Try naming the object, mission, or space topic you mean.'}
    excerpt, title, href = result
    return {'reply': f'NASA’s “{title}” has this related passage.\n\n“{excerpt}”',
            'space_topic': topic if topic and REFERENCE.search(message.lower()) else query,
            'sources': [{'label': f'NASA · {title}', 'href': href}]}
