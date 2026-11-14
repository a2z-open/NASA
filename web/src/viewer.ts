import './style.css';
import { compareFrames, parseCoordinates, sortFrames, type Coordinates, type Frame, type Sequence } from './sequence';

interface Target {
  slug: string;
  title: string;
  kind: string;
  position: Coordinates;
}

const targets: Target[] = [
  { slug: 'barnards-star', title: 'Barnard’s Star', kind: 'Nearby star', position: { ra: 269.4463, dec: 4.7685 } },
  { slug: 'epsilon-indi-b', title: 'Epsilon Indi B', kind: 'Brown dwarf pair', position: { ra: 331.0441466, dec: -56.7828442 } },
  { slug: 'wise-0855', title: 'WISE 0855', kind: 'Brown dwarf', position: { ra: 133.7951292, dec: -7.2451472 } },
  { slug: 'rw-aurigae', title: 'RW Aurigae', kind: 'Variable star', position: { ra: 76.95654, dec: 30.40144 } },
  { slug: 'r-draconis', title: 'R Draconis', kind: 'Variable star', position: { ra: 248.1676108, dec: 66.7549794 } },
];

const calendarDate = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' });
const frameDate = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });
const observationTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const statusLabels = {
  ready: 'Observations ready',
  one_visit: 'Only one visit available',
  no_coverage: 'No observations found',
  no_usable_frames: 'No images available for playback',
  archive_unavailable: 'Archive temporarily unavailable',
};

function element<T extends HTMLElement = HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

const heading = element('observation-title');
const caption = element('field-caption');
const image = document.createElement('img');
image.hidden = true;
image.id = 'sky-image';
element('viewport').prepend(image);
const timeline = element<HTMLOListElement>('timeline');
const play = element<HTMLButtonElement>('play');
const previous = element<HTMLButtonElement>('previous');
const next = element<HTMLButtonElement>('next');
const raInput = element<HTMLInputElement>('ra');
const decInput = element<HTMLInputElement>('dec');
const search = element<HTMLButtonElement>('search');
const copyLink = element<HTMLButtonElement>('copy-link');
const formError = element('form-error');
const announcement = element('announcement');
const targetList = element<HTMLUListElement>('targets');
let sequence: Sequence | undefined;
let frameIndex = 0;
let timer: number | undefined;
let request: AbortController | undefined;
let imageVersion = 0;
const keepImages = new Map<string, HTMLImageElement>();

function displayDate(formatter: Intl.DateTimeFormat, utc: string): string {
  const date = new Date(utc);
  return Number.isFinite(date.getTime()) ? formatter.format(date) : 'Time unavailable';
}

function showMessage(title: string, detail: string, loading = false) {
  image.hidden = true;
  element('orientation').hidden = true;
  const message = element('image-message');
  message.hidden = false;
  message.dataset.loading = String(loading);
  element('message-title').textContent = title;
  element('message-detail').textContent = detail;
}

function updateControls() {
  const count = sequence?.frames.length ?? 0;
  previous.disabled = count < 2;
  next.disabled = count < 2;
  play.disabled = count < 2;
  const playing = timer !== undefined;
  play.setAttribute('aria-label', playing ? 'Pause observations' : 'Play observations');
  element('play-label').textContent = playing ? 'Pause' : 'Play';
  element('play-icon').hidden = playing;
  element('pause-icon').hidden = !playing;
}

function pause() {
  window.clearInterval(timer);
  timer = undefined;
  updateControls();
}

function imageFor(frame: Frame): HTMLImageElement {
  const saved = keepImages.get(frame.display_url);
  if (saved) return saved;
  const loading = new Image();
  loading.src = frame.display_url;
  keepImages.set(frame.display_url, loading);
  return loading;
}

function frameDialogText(frame: Frame): string {
  return `${displayDate(calendarDate, frame.time_utc)} · ${displayDate(observationTime, frame.time_utc)} UTC`;
}

function showImage(frame: Frame) {
  const version = ++imageVersion;
  const candidate = imageFor(frame);
  const present = () => {
    if (imageVersion !== version) return;
    image.src = candidate.src;
    image.alt = `SPHEREx image of ${heading.textContent} from ${displayDate(calendarDate, frame.time_utc)}`;
    image.hidden = false;
    element('image-message').hidden = true;
    element('orientation').hidden = false;
  };
  const fail = () => {
    if (imageVersion !== version) return;
    pause();
    keepImages.delete(frame.display_url);
    showMessage('Image unavailable', 'Select another observation to continue.');
    announcement.textContent = 'The selected observation image did not load.';
  };
  if (candidate.complete) {
    if (candidate.naturalWidth) present();
    else fail();
  } else {
    showMessage('Opening observation', frameDialogText(frame), true);
    void candidate.decode().then(present, fail);
  }
}

function renderFrame(newIndex: number, announce = true) {
  if (!sequence?.frames.length) return;
  const frames = sequence.frames;
  frameIndex = (newIndex + frames.length) % frames.length;
  const frame = frames[frameIndex];
  showImage(frame);
  timeline.querySelectorAll('button').forEach((button, index) => {
    if (index === frameIndex) {
      button.setAttribute('aria-current', 'true');
      if (timeline.scrollWidth > timeline.clientWidth) {
        const left = button.getBoundingClientRect().left - timeline.getBoundingClientRect().left;
        const right = left + button.offsetWidth;
        if (left < 0 || right > timeline.clientWidth) {
          timeline.scrollLeft += left < 0 ? left : right - timeline.clientWidth;
        }
      }
    } else button.removeAttribute('aria-current');
  });
  const date = frameDialogText(frame);
  const dateReadout = element<HTMLTimeElement>('date-readout');
  dateReadout.dateTime = frame.time_utc;
  dateReadout.textContent = date;
  element('detector-readout').textContent = String(frame.detector).replace(/^D(?:etector\s+)?(\d+)$/i, 'D$1').replace(/^(\d+)$/, 'D$1');
  const wave = frame.wavelength_um;
  element('wave-readout').textContent = typeof wave === 'number' && Number.isFinite(wave)
    ? `${frame.wavelength_verified === true ? '' : '≈ '}${wave.toFixed(3)} µm`
    : 'Unverified';
  element('frame-count').textContent = `${frameIndex + 1} of ${frames.length}`;
  const pairing = compareFrames(sequence, frameIndex);
  const visitCount = new Set(frames.map(item => item.visit_id)).size;
  element('comparison-readout').textContent = visitCount === 1 ? 'One visit available' : {
    matched: 'Bandpass matched to first frame',
    unmatched: 'Bandpass differs from first frame',
    unverified: 'Bandpass match unverified',
  }[pairing];
  const archiveRecord = element<HTMLAnchorElement>('archive-record');
  archiveRecord.hidden = !/^https:\/\//.test(frame.archive_url);
  if (!archiveRecord.hidden) archiveRecord.href = frame.archive_url;
  if (announce) announcement.textContent = `Observation ${frameIndex + 1} of ${frames.length}, ${date}.`;
}

function renderTimeline(frames: Frame[]) {
  const crossesYears = new Set(frames.map(frame => frame.time_utc.slice(0, 4))).size > 1;
  const dateOccurrences = new Map<string, number>();
  for (const frame of frames) {
    const date = frame.time_utc.slice(0, 10);
    dateOccurrences.set(date, (dateOccurrences.get(date) ?? 0) + 1);
  }
  timeline.replaceChildren(...frames.map((frame, index) => {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = displayDate(crossesYears ? calendarDate : frameDate, frame.time_utc);
    if ((dateOccurrences.get(frame.time_utc.slice(0, 10)) ?? 0) > 1) {
      const time = document.createElement('span');
      time.className = 'timeline-time';
      time.textContent = displayDate(observationTime, frame.time_utc);
      button.append(time);
    }
    button.title = frameDialogText(frame);
    button.setAttribute('aria-label', `Observation ${index + 1}, ${frameDialogText(frame)}`);
    button.addEventListener('click', () => {
      pause();
      renderFrame(index);
    });
    item.append(button);
    return item;
  }));
}

async function readSequence(path: string, signal: AbortSignal): Promise<Sequence> {
  const response = await fetch(path, { signal, headers: { accept: 'application/json' } });
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new Error('No saved observations were returned.');
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || 'The observation request failed.');
  if (!Array.isArray(result.frames) || !Object.hasOwn(statusLabels, result.status)) {
    throw new Error('IRSA did not return a usable observation sequence.');
  }
  result.frames = sortFrames(result.frames);
  return result;
}

function setPageAddress(target: Target | undefined, position: Coordinates) {
  const address = new URL(window.location.href);
  address.search = '';
  if (target) address.searchParams.set('target', target.slug);
  else {
    address.searchParams.set('ra', String(position.ra));
    address.searchParams.set('dec', String(position.dec));
  }
  window.history.replaceState({}, '', address);
}

async function loadField(position: Coordinates, target?: Target) {
  request?.abort();
  const current = new AbortController();
  request = current;
  sequence = undefined;
  keepImages.clear();
  imageVersion += 1;
  pause();
  heading.textContent = target?.title ?? 'Sky field';
  caption.textContent = `RA ${position.ra.toFixed(4)}° · Dec ${position.dec.toFixed(4)}° · ICRS`;
  raInput.value = String(position.ra);
  decInput.value = String(position.dec);
  clearFormError();
  targetList.querySelectorAll('button').forEach(button => {
    if (button.value === target?.slug) button.setAttribute('aria-current', 'true');
    else button.removeAttribute('aria-current');
  });
  setPageAddress(target, position);
  search.disabled = true;
  copyLink.hidden = true;
  element('frame-source').textContent = 'SPHEREx Level 2';
  element('frame-count').textContent = '';
  element('observation-information').hidden = true;
  timeline.replaceChildren();
  announcement.textContent = `Opening observations for ${heading.textContent}.`;
  showMessage('Opening observations', target ? 'Loading the saved sky field.' : 'Searching the NASA/IPAC archive.', true);

  const query = `/api/sequence?${new URLSearchParams({ ra: String(position.ra), dec: String(position.dec) })}`;
  try {
    let result: Sequence;
    if (target) {
      try {
        result = await readSequence(`/data/${target.slug}.json`, current.signal);
      } catch (error) {
        if (current.signal.aborted) return;
        if (target.slug === 'barnards-star') throw error;
        result = await readSequence(query, current.signal);
      }
    } else result = await readSequence(query, current.signal);
    if (current.signal.aborted) return;
    sequence = result;
    copyLink.hidden = false;
    if (!result.frames.length) {
      const detail = result.message ?? 'Try another field or choose a target.';
      const action = target && result.status === 'no_usable_frames' ? ' Choose Find observations to query IRSA.' : '';
      showMessage(statusLabels[result.status], detail + action);
      announcement.textContent = statusLabels[result.status];
      return;
    }
    element('frame-source').textContent = result.source === 'cache' ? 'SPHEREx Level 2 · Saved sequence' : 'SPHEREx Level 2 · IRSA archive';
    const observationNote = element('observation-note');
    observationNote.textContent = result.message ?? '';
    observationNote.hidden = !result.message;
    renderTimeline(result.frames);
    for (const frame of result.frames) imageFor(frame);
    element('observation-information').hidden = false;
    renderFrame(0);
  } catch {
    if (current.signal.aborted) return;
    const text = target?.slug === 'barnards-star'
      ? 'The saved Barnard’s Star sequence is unavailable. Try another target.'
      : 'Try a saved target or search again.';
    showMessage('Observations unavailable', text);
    announcement.textContent = `Observations unavailable. ${text}`;
  } finally {
    if (request === current) search.disabled = false;
    updateControls();
  }
}

function clearFormError() {
  formError.hidden = true;
  raInput.removeAttribute('aria-invalid');
  decInput.removeAttribute('aria-invalid');
}

for (const target of targets) {
  const row = document.createElement('li');
  const button = document.createElement('button');
  const labels = document.createElement('span');
  const name = document.createElement('span');
  const kind = document.createElement('span');
  button.type = 'button';
  button.value = target.slug;
  name.className = 'target-name';
  name.textContent = target.title;
  kind.className = 'target-kind';
  kind.textContent = target.kind;
  labels.append(name, kind);
  button.append(labels);
  row.append(button);
  targetList.append(row);
  button.addEventListener('click', () => {
    void loadField(target.position, target);
    heading.focus();
  });
}

const advance = (direction: number) => {
  pause();
  renderFrame(frameIndex + direction);
};

previous.addEventListener('click', () => advance(-1));
next.addEventListener('click', () => advance(1));
play.addEventListener('click', () => {
  if (timer !== undefined) return pause();
  if ((sequence?.frames.length ?? 0) < 2) return;
  timer = window.setInterval(() => renderFrame(frameIndex + 1, false), 1150);
  updateControls();
});

element('viewport').addEventListener('keydown', event => {
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();
    advance(event.key === 'ArrowLeft' ? -1 : 1);
  } else if (event.key === ' ' && !play.disabled) {
    event.preventDefault();
    play.click();
  }
});

element<HTMLFormElement>('lookup-form').addEventListener('submit', event => {
  event.preventDefault();
  clearFormError();
  try {
    const position = parseCoordinates(raInput.value, decInput.value);
    void loadField(position);
    heading.focus();
  } catch (error) {
    const message = (error as Error).message;
    formError.textContent = message;
    formError.hidden = false;
    const invalid = /^declination/i.test(message) || (raInput.value.trim() && !decInput.value.trim()) ? decInput : raInput;
    invalid.setAttribute('aria-invalid', 'true');
    invalid.focus();
  }
});

raInput.addEventListener('input', clearFormError);
decInput.addEventListener('input', clearFormError);
document.addEventListener('visibilitychange', () => { if (document.hidden) pause(); });
copyLink.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(window.location.href);
    copyLink.textContent = 'Link copied';
    announcement.textContent = 'Field link copied.';
    window.setTimeout(() => { copyLink.textContent = 'Copy field link'; }, 1400);
  } catch {
    announcement.textContent = 'Copy the field link from your browser address bar.';
    copyLink.textContent = 'Use address bar link';
  }
});

const params = new URLSearchParams(window.location.search);
const initialTarget = targets.find(target => target.slug === params.get('target')) ?? targets[0];
try {
  if (!params.has('target') && (params.has('ra') || params.has('dec'))) {
    void loadField(parseCoordinates(params.get('ra') ?? '', params.get('dec') ?? ''));
  } else void loadField(initialTarget.position, initialTarget);
} catch {
  void loadField(initialTarget.position, initialTarget);
}
