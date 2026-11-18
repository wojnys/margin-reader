// Run from any directory. Export imports the app factory without starting its lifespan.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('..', import.meta.url));
const frontend = path.join(root, 'frontend');
const uv = existsSync(path.join(root, '.tools/uv')) ? path.join(root, '.tools/uv') : 'uv';
const orval = path.join(frontend, 'node_modules/orval/dist/bin/orval.mjs');
const mode = process.argv[2] || 'generate';
function run(command, args, cwd = root) {
  const result = spawnSync(command, args, { cwd, stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
function snapshot(directory) {
  const files = readdirSync(directory, { withFileTypes: true }).sort((a,b) => a.name.localeCompare(b.name));
  return files.flatMap(entry => entry.isDirectory() ? snapshot(path.join(directory, entry.name)) : [[path.relative(root, path.join(directory, entry.name)), readFileSync(path.join(directory, entry.name), 'utf8')]]);
}
if (mode === 'watch') {
  run(uv, ['run', '--locked', 'python', '-m', 'backend.app.tools.export_openapi']);
  const children = [
    spawn(uv, ['run', '--locked', 'python', '-m', 'backend.app.tools.watch_openapi'], {cwd: root, stdio: 'inherit'}),
    spawn(process.execPath, [orval, '--watch'], {cwd: frontend, stdio: 'inherit'}),
  ];
  let stopping = false;
  function stop(code) { if (stopping) return; stopping = true; for (const child of children) child.kill('SIGTERM'); process.exitCode = code; }
  process.on('SIGINT', () => stop(0)); process.on('SIGTERM', () => stop(0));
  for (const child of children) { child.on('error', () => stop(1)); child.on('exit', code => stop(code || 0)); }
} else {
  if (!['generate', 'check'].includes(mode)) throw new Error('Use generate, check, or watch');
  const target = path.join(frontend, 'src/api/generated');
  const before = mode === 'check' && existsSync(target) ? JSON.stringify(snapshot(target)) : null;
  run(uv, ['run', '--locked', 'python', '-m', 'backend.app.tools.export_openapi', ...(mode === 'check' ? ['--check'] : [])]);
  run(process.execPath, [orval], frontend);
  if (mode === 'check' && before !== JSON.stringify(snapshot(target))) {
    console.error('Generated client was stale; regenerated it. Review and commit the generated changes.');
    process.exitCode = 1;
  }
}
