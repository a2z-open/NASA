"""Contact sheet of a clip: frames every `step` seconds, labelled with their time.  Usage: sheet.py clip.mp4 out.png step"""
import subprocess, sys, tempfile, os
from PIL import Image, ImageDraw
clip, out, step = sys.argv[1], sys.argv[2], float(sys.argv[3])
dur = float(subprocess.check_output(['npx', 'remotion', 'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', clip], text=True).strip())
tiles, t = [], 0.3
with tempfile.TemporaryDirectory() as d:
    while t < dur:
        p = os.path.join(d, f'{t:07.2f}.png')
        subprocess.run(['npx', 'remotion', 'ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{t:.2f}', '-i', clip, '-frames:v', '1', p], check=True)
        im = Image.open(p).convert('RGB').resize((480, 270))
        ImageDraw.Draw(im).text((8, 6), f'{t:.1f}s', fill=(255, 80, 80))
        tiles.append(im); t += step
cols = 4; rows = (len(tiles) + cols - 1) // cols
sheet = Image.new('RGB', (cols * 480, rows * 270))
for i, im in enumerate(tiles): sheet.paste(im, ((i % cols) * 480, (i // cols) * 270))
sheet.save(out); print(out, len(tiles), 'frames', f'{dur:.1f}s')
