import { reencode } from './rec.mjs';
import { execFileSync } from 'node:child_process';
for (const n of process.argv.slice(2)) {
  const out = reencode(n);
  const d = execFileSync('npx', ['remotion', 'ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=width,height,r_frame_rate,nb_frames', '-of', 'csv=p=0', out], { encoding: 'utf8' });
  console.log(n, d.trim().replace(/\n/g, ' | '));
}
