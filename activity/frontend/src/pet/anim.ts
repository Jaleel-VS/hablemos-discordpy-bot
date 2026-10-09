// Animator: a small deterministic state machine that turns (mood, time, input) into a Pose.
// Pure: `step()` takes the previous state and a timestamp and returns the next state. The component
// owns the clock; tests can drive it by hand.
import { bodyTop, clamp01, GRID, type Palette, type Species, SPECIES_SPECS } from "./model";
import type { Mouth, Particle, Pose } from "./raster";

/** What the agent is doing; drives the ambient animation. */
export type Mood = "idle" | "working" | "error";

/** One-shot reactions; each plays once then returns to the ambient loop. */
export type Reaction = "hop" | "squish" | "dizzy" | "love";

export type AnimState = {
	readonly mood: Mood;
	/** Milliseconds since the component mounted; all periodic motion is a function of this. */
	readonly t: number;
	/** The active one-shot and when it started. */
	readonly reaction: { kind: Reaction; since: number } | undefined;
	/** When the next blink begins; rescheduled after each blink. */
	readonly nextBlink: number;
	/** Where the critter wants to look; eased toward by `gaze`. */
	readonly target: { x: number; y: number };
	readonly gaze: { x: number; y: number };
	/** A deterministic PRNG seed so blinks and particles differ per critter but replay the same. */
	readonly seed: number;
};

const REACTION_MS: Record<Reaction, number> = { hop: 520, squish: 380, dizzy: 1100, love: 900 };

export function initial(seed: number, now = 0): AnimState {
	return { mood: "idle", t: now, reaction: undefined, nextBlink: now + 1800 + (seed % 1000), target: { x: 0, y: 0 }, gaze: { x: 0, y: 0 }, seed };
}

/** Deterministic hash → [0, 1). */
function noise(seed: number, n: number): number {
	let h = (seed ^ (n * 0x9e3779b1)) >>> 0;
	h = Math.imul(h ^ (h >>> 16), 0x85ebca6b) >>> 0;
	h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35) >>> 0;
	return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export function setMood(state: AnimState, mood: Mood): AnimState {
	if (state.mood === mood) return state;
	// Finishing work earns a hop; failing earns a squish. Both read as "something happened".
	const reaction = state.mood === "working" && mood === "idle" ? "hop" : mood === "error" ? "squish" : undefined;
	return { ...state, mood, reaction: reaction === undefined ? state.reaction : { kind: reaction, since: state.t } };
}

export function react(state: AnimState, kind: Reaction): AnimState {
	return { ...state, reaction: { kind, since: state.t } };
}

/** Point the eyes at a position in [-1, 1]²; `undefined` looks ahead. */
export function lookAt(state: AnimState, target: { x: number; y: number } | undefined): AnimState {
	return { ...state, target: target ?? { x: 0, y: 0 } };
}

export function step(state: AnimState, now: number): AnimState {
	const dt = Math.min(100, Math.max(0, now - state.t));
	const k = 1 - Math.exp(-dt / 90); // gaze easing
	const gaze = { x: state.gaze.x + (state.target.x - state.gaze.x) * k, y: state.gaze.y + (state.target.y - state.gaze.y) * k };
	let { nextBlink, reaction } = state;
	if (now > nextBlink + 700) nextBlink = now + 1600 + noise(state.seed, Math.floor(now / 100)) * 3200; // after both blink pulses have fully ended
	if (reaction !== undefined && now - reaction.since > REACTION_MS[reaction.kind]) reaction = undefined;
	return { ...state, t: now, gaze, nextBlink, reaction };
}

/** Smooth 0→1→0 over a duration, with zero slope at both ends so coarse frames never snap. */
function pulse(progress: number): number {
	return Math.sin(Math.PI * clamp01(progress)) ** 2;
}

export function pose(state: AnimState, species: Species, palette: Palette): Pose {
	const { t, mood } = state;
	const spec = SPECIES_SPECS[species];
	const particles: Particle[] = [];
	let scaleX = 1;
	let scaleY = 1;
	let lift = 0;
	let mouth: Mouth = "flat";
	let blush = false;
	let gaze = state.gaze;

	// Ambient: breathing, faster and bouncier while working.
	const breath = mood === "working" ? Math.sin(t / 140) : Math.sin(t / 650);
	scaleY += breath * (mood === "working" ? 0.045 : 0.02);
	scaleX -= breath * (mood === "working" ? 0.03 : 0.012);
	if (mood === "working") {
		lift -= Math.max(0, Math.sin(t / 140)) * 2;
		mouth = "o";
		// Three thinking dots cycling above the right shoulder.
		const phase = Math.floor(t / 220) % 4;
		for (let i = 0; i < Math.min(3, phase); i++) particles.push({ x: GRID / 2 + spec.half.x - 2 + i * 3, y: bodyTop(species) - 3 - (i % 2), color: palette.highlight, shape: "dot" });
	} else if (mood === "error") {
		scaleY *= 0.94;
		scaleX *= 1.04;
		mouth = "flat";
		particles.push({ x: GRID / 2 + spec.half.x - 1, y: bodyTop(species) + 3 + (Math.floor(t / 300) % 2), color: [120, 180, 255], shape: "dot" });
	} else {
		mouth = "smile";
	}

	// Blink: a 300 ms close-hold-open pulse (≥4 frames at 15 fps, so no frame snaps the eye open).
	// One time in four a second pulse follows after a short gap.
	let blink = 0;
	const sinceBlink = t - state.nextBlink;
	if (sinceBlink >= 0 && sinceBlink < 300) blink = pulse(sinceBlink / 300);
	else if (sinceBlink >= 340 && sinceBlink < 640 && noise(state.seed, Math.floor(state.nextBlink)) < 0.25) blink = pulse((sinceBlink - 340) / 300);

	// Reactions override the ambient loop.
	if (state.reaction !== undefined) {
		const p = (t - state.reaction.since) / REACTION_MS[state.reaction.kind];
		switch (state.reaction.kind) {
			case "hop": {
				// Anticipation squash, jump, land with a little splat.
				if (p < 0.2) {
					scaleY *= 1 - 0.18 * pulse(p / 0.2);
					scaleX *= 1 + 0.12 * pulse(p / 0.2);
				} else {
					const air = pulse((p - 0.2) / 0.8);
					lift -= air * 5;
					scaleY *= 1 + 0.1 * air;
					scaleX *= 1 - 0.06 * air;
				}
				mouth = "smile";
				blush = true;
				break;
			}
			case "squish": {
				scaleY *= 1 - 0.3 * pulse(p);
				scaleX *= 1 + 0.22 * pulse(p);
				mouth = "o";
				blink = Math.max(blink, pulse(p) > 0.5 ? 1 : 0);
				break;
			}
			case "dizzy": {
				const spin = t / 120;
				gaze = { x: Math.cos(spin) * 0.9, y: Math.sin(spin) * 0.9 };
				scaleX *= 1 + 0.03 * Math.sin(t / 60);
				mouth = "o";
				for (let i = 0; i < 3; i++) {
					const a = spin + (i * 2 * Math.PI) / 3;
					particles.push({ x: GRID / 2 + Math.cos(a) * (spec.half.x * 0.7), y: bodyTop(species) - 3 + Math.sin(a) * 2, color: [255, 220, 90], shape: "plus" });
				}
				break;
			}
			case "love": {
				blush = true;
				mouth = "smile";
				scaleY *= 1 + 0.06 * Math.sin(p * Math.PI * 3);
				// Hearts rise toward the top edge but never past it.
				const rise = Math.min(p * 10, bodyTop(species) - 2);
				for (let i = 0; i < 3; i++) {
					const jitter = noise(state.seed, i) * 2 - 1;
					particles.push({ x: GRID / 2 + (i - 1) * 7 + jitter, y: bodyTop(species) - 2 - rise + i * 2, color: [255, 120, 150], shape: "plus" });
				}
				break;
			}
		}
	}

	return { species, palette, scaleX, scaleY, lift, gaze, blink, mouth, blush, particles };
}
