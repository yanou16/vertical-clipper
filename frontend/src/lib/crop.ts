/** Width of the 9:16 window as a fraction of the source width. */
export function cropWidthFraction(width: number, height: number): number {
  return Math.min(1, (height * 9) / 16 / width);
}

/**
 * The camera path made from a clip's manual framing points. Mirrors the server's `effective_path`:
 * the window is kept inside the frame, and before/after the points the camera holds still.
 */
export function framingPath(keyframes: [number, number][], cropFrac: number): [number, number][] {
  const half = cropFrac / 2;
  return [...keyframes]
    .sort((a, b) => a[0] - b[0])
    .map(([t, c]): [number, number] => [t, Math.min(Math.max(c, half), 1 - half)]);
}

/** Camera centre (0..1) at time t. Mirrors the server's np.interp over the same path. */
export function centerAt(path: [number, number][], t: number): number {
  if (path.length === 0) return 0.5;
  if (t <= path[0][0]) return path[0][1];
  const last = path[path.length - 1];
  if (t >= last[0]) return last[1];
  let lo = 0;
  let hi = path.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (path[mid][0] <= t) lo = mid;
    else hi = mid;
  }
  const [t0, c0] = path[lo];
  const [t1, c1] = path[hi];
  return t1 === t0 ? c1 : c0 + ((c1 - c0) * (t - t0)) / (t1 - t0);
}
