// <Pet>: one animated critter on a canvas. Every mounted Pet shares a single
// 15fps ticker so a hub plus a leaderboard full of them costs one timer. The
// animation state is pure (anim.ts); this file owns only the clock, the canvas,
// and pointer events. Ported from the `ani` project's Preact <Critter>.
import { useEffect, useMemo, useRef } from "react";
import { initial, lookAt, type Mood, pose, type Reaction, react, setMood, step } from "./anim";
import { GRID, paletteFor, type Species } from "./model";
import { rasterize } from "./raster";

const FPS = 15;
const subscribers = new Set<(now: number) => void>();
let timer: number | undefined;
const epoch = performance.now();

function subscribe(tick: (now: number) => void): () => void {
  subscribers.add(tick);
  timer ??= window.setInterval(() => {
    const now = performance.now() - epoch;
    for (const s of subscribers) s(now);
  }, 1000 / FPS);
  return () => {
    subscribers.delete(tick);
    if (subscribers.size === 0 && timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

export type { Mood, Reaction, Species };

export interface PetProps {
  species: Species;
  color: string;
  /** Display size in CSS px; drawn at the nearest integer multiple of GRID for crisp pixels. */
  size: number;
  mood?: Mood;
  /** React to the pointer (gaze, tap). Off for tiny list avatars. */
  interactive?: boolean;
  /** Changing `n` plays the reaction once (pass a counter). The mount value never plays. */
  cue?: { kind: Reaction; n: number };
  label?: string;
  className?: string;
}

export default function Pet(props: PetProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const seed = useMemo(
    () => Array.from(props.species + props.color).reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7),
    [props.species, props.color],
  );
  const palette = useMemo(() => paletteFor(props.color), [props.color]);
  const state = useRef(initial(seed, performance.now() - epoch));
  const mood = props.mood ?? "idle";
  const scale = Math.max(1, Math.round(props.size / GRID));
  const px = GRID * scale;

  useEffect(() => {
    state.current = setMood(state.current, mood);
  }, [mood]);

  const seenCue = useRef(props.cue?.n);
  useEffect(() => {
    if (props.cue === undefined || props.cue.n === seenCue.current) return;
    seenCue.current = props.cue.n;
    state.current = react(state.current, props.cue.kind);
  }, [props.cue]);

  useEffect(() => {
    const element = canvas.current;
    if (element === null) return;
    const ctx = element.getContext("2d");
    if (ctx === null) return;
    const image = new ImageData(GRID, GRID);
    const offscreen = new OffscreenCanvas(GRID, GRID);
    const octx = offscreen.getContext("2d");
    if (octx === null) return;
    ctx.imageSmoothingEnabled = false;
    return subscribe((now) => {
      state.current = step(state.current, now);
      image.data.set(rasterize(pose(state.current, props.species, palette)));
      octx.putImageData(image, 0, 0);
      ctx.clearRect(0, 0, px, px);
      ctx.drawImage(offscreen, 0, 0, px, px);
    });
  }, [props.species, palette, px]);

  const interactive = props.interactive ?? false;
  return (
    <canvas
      ref={canvas}
      width={px}
      height={px}
      className={`pet${interactive ? " pet--interactive" : ""}${props.className ? ` ${props.className}` : ""}`}
      style={{ width: `${px}px`, height: `${px}px` }}
      role="img"
      aria-label={props.label}
      onPointerMove={
        interactive
          ? (event) => {
              const r = event.currentTarget.getBoundingClientRect();
              const x = ((event.clientX - r.left) / r.width) * 2 - 1;
              const y = ((event.clientY - r.top) / r.height) * 2 - 1;
              state.current = lookAt(state.current, {
                x: Math.max(-1, Math.min(1, x)),
                y: Math.max(-1, Math.min(1, y)),
              });
            }
          : undefined
      }
      onPointerLeave={interactive ? () => (state.current = lookAt(state.current, undefined)) : undefined}
      onClick={
        interactive
          ? () => {
              // Mostly affection, sometimes a surprised squish, so it doesn't feel scripted.
              state.current = react(state.current, Math.random() < 0.75 ? "love" : "squish");
            }
          : undefined
      }
    />
  );
}
