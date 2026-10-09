// Rasterizer: a Pose → RGBA pixels on the GRID. Pure and deterministic, so the same pose always
// gives the same picture. The look: one light from the top-left, six palette bands with ordered
// dither between them, a 1px outline, big two-tone eyes with catchlights, a soft ground shadow.
import { GRID, GROUND_Y, type Palette, type Rgb, SPECIES_SPECS, type Species } from "./model";

export type Mouth = "flat" | "smile" | "o";

export type Particle = { x: number; y: number; color: Rgb; shape: "dot" | "plus" };

export type Pose = {
	species: Species;
	palette: Palette;
	/** Squash and stretch; 1 is rest. */
	scaleX: number;
	scaleY: number;
	/** Vertical offset in pixels; negative is up (hop). The shadow stays on the ground. */
	lift: number;
	/** Where the pupils look, each in [-1, 1]. */
	gaze: { x: number; y: number };
	/** 0 open … 1 closed. */
	blink: number;
	mouth: Mouth;
	blush: boolean;
	particles: readonly Particle[];
};

const LIGHT = normalize([-0.55, -0.75, 0.6]);
const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5] as const; // 4×4 ordered dither
const SHADOW_ALPHA = 70;
const BLUSH: Rgb = [255, 150, 170];
const LEAF: Rgb = [96, 190, 110];
const LEAF_DARK: Rgb = [52, 130, 72];

function normalize([x, y, z]: readonly [number, number, number]): readonly [number, number, number] {
	const n = Math.hypot(x, y, z);
	return [x / n, y / n, z / n];
}

/** Body test in normalized coordinates u, v ∈ [-1, 1] (left→right, top→bottom). */
function inside(species: Species, u: number, v: number): boolean {
	switch (species) {
		case "blob": {
			const w = 1 + 0.22 * Math.max(0, v); // wider toward the ground
			return (u / w) ** 2 + v ** 2 <= 1;
		}
		case "drop": {
			const t = (v + 1) / 2;
			const w = t <= 0.52 ? (t / 0.52) ** 0.9 : Math.sqrt(Math.max(0, 1 - ((t - 0.52) / 0.48) ** 2));
			return Math.abs(u) <= w;
		}
		case "orb":
			return u ** 2 + v ** 2 <= 1;
		case "sprout":
			return u ** 2 + v ** 2 <= 1;
		case "ghost": {
			if (v <= 0) return u ** 2 + v ** 2 <= 1;
			if (Math.abs(u) > 1) return false;
			const hem = 1 - 0.14 * (1 + Math.cos(u * Math.PI * 3)); // three scallops
			return v <= hem;
		}
		case "bun": {
			// A circle cut flat at the bottom, scaled so the flat sits on the ground.
			const vv = (v + 1) * 0.89 - 1;
			return u ** 2 + vv ** 2 <= 1 && vv <= 0.78;
		}
		case "star": {
			// Five-point star, one point up. In unit space the top point is at y = -1 and the two lower points at
			// y = cos(36°) ≈ 0.81; v is mapped so those lower points stand on the ground (v = 1).
			const y = -1 + (v + 1) * (1.809 / 2);
			const outer = 1;
			const inner = 0.62;
			const step = (2 * Math.PI) / 5;
			let a = Math.atan2(u, -y); // 0 at the top point (y = -1 is up on screen), increasing clockwise
			a = ((a % step) + step) % step;
			const m = Math.abs(a - step / 2);
			const half = step / 2;
			const edge = (outer * inner * Math.sin(half)) / (inner * Math.sin(half - m) + outer * Math.sin(m));
			return Math.hypot(u, y) <= edge;
		}
		case "mochi": {
			const vv = (v + 1) * 0.95 - 1;
			return u ** 2 + vv ** 2 <= 1 && vv <= 0.9;
		}
		case "cube":
			return Math.abs(u) ** 5 + Math.abs(v) ** 5 <= 1;
		case "pebble":
			return (u + 0.18 * v) ** 2 + v ** 2 <= 1;
	}
}

/** Shade band 0 (dark) … 4 (highlight) for a pseudo-normal. Dither only near a band boundary, so the bands read as solid. */
function band(nx: number, ny: number, px: number, py: number): number {
	const nz = Math.sqrt(Math.max(0, 1 - nx * nx - ny * ny));
	const lambert = (nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2] + 1) / 2; // 0…1
	const level = lambert * 4.4 - 0.5;
	const frac = level - Math.floor(level);
	const threshold = (BAYER[(py & 3) * 4 + (px & 3)]! + 0.5) / 16;
	const bump = frac > 0.82 && (frac - 0.82) / 0.18 > threshold;
	return Math.max(0, Math.min(4, Math.floor(level) + (bump ? 1 : 0)));
}

export function rasterize(pose: Pose): Uint8ClampedArray {
	const pixels = new Uint8ClampedArray(GRID * GRID * 4);
	const spec = SPECIES_SPECS[pose.species];
	const hx = spec.half.x * pose.scaleX;
	const hy = spec.half.y * pose.scaleY;
	const groundY = GROUND_Y;
	// Body center: the bottom edge is the shadow line, so the last body row (sampled at y + 0.5) is groundY - 1.
	const cy = groundY - hy + pose.lift;
	const cx = GRID / 2;
	const bands: Rgb[] = [pose.palette.dark, pose.palette.shade, pose.palette.base, pose.palette.light, pose.palette.highlight];

	const put = (x: number, y: number, [r, g, b]: Rgb, a = 255): void => {
		x = Math.round(x);
		y = Math.round(y);
		if (x < 0 || y < 0 || x >= GRID || y >= GRID) return;
		const i = (y * GRID + x) * 4;
		pixels[i] = r;
		pixels[i + 1] = g;
		pixels[i + 2] = b;
		pixels[i + 3] = a;
	};

	// Shadow first, so the body paints over it.
	const sw = spec.half.x * 0.85 * (1 - Math.min(0.5, Math.max(0, -pose.lift) / 20));
	for (let x = 0; x < GRID; x++) {
		const u = (x + 0.5 - cx) / sw;
		if (Math.abs(u) <= 1) put(x, groundY, [0, 0, 0], Math.round(SHADOW_ALPHA * (1 - u * u * 0.6)));
		if (Math.abs(u) <= 0.6) put(x, groundY + 1, [0, 0, 0], Math.round(SHADOW_ALPHA * 0.5));
	}

	// Body mask and per-row extents (for a generic pseudo-normal).
	const mask = new Uint8Array(GRID * GRID);
	const rowMin = new Int16Array(GRID).fill(GRID);
	const rowMax = new Int16Array(GRID).fill(-1);
	for (let y = 0; y < GRID; y++) {
		const v = (y + 0.5 - cy) / hy;
		if (v < -1.02 || v > 1.02) continue;
		for (let x = 0; x < GRID; x++) {
			const u = (x + 0.5 - cx) / hx;
			if (Math.abs(u) > 1.02) continue;
			if (inside(pose.species, u, v)) {
				mask[y * GRID + x] = 1;
				if (x < rowMin[y]!) rowMin[y] = x;
				if (x > rowMax[y]!) rowMax[y] = x;
			}
		}
	}
	const isBody = (x: number, y: number): boolean => x >= 0 && y >= 0 && x < GRID && y < GRID && mask[y * GRID + x] === 1;

	for (let y = 0; y < GRID; y++) {
		for (let x = 0; x < GRID; x++) {
			if (!isBody(x, y)) continue;
			const edge = !isBody(x - 1, y) || !isBody(x + 1, y) || !isBody(x, y - 1) || !isBody(x, y + 1);
			if (edge) {
				put(x, y, pose.palette.outline);
				continue;
			}
			const rowHalf = Math.max(1, (rowMax[y]! - rowMin[y]! + 1) / 2);
			const nx = (x + 0.5 - (rowMin[y]! + rowHalf)) / rowHalf;
			const ny = (y + 0.5 - cy) / hy;
			put(x, y, bands[band(nx, ny, x, y)]!);
		}
	}

	// Species decoration: a sprout's stem and leaf.
	if (pose.species === "sprout") {
		const top = Math.round(cy - hy);
		put(cx - 0.5, top - 1, LEAF_DARK);
		put(cx - 0.5, top - 2, LEAF_DARK);
		put(cx + 0.5, top - 3, LEAF);
		put(cx + 1.5, top - 3, LEAF);
		put(cx + 1.5, top - 4, LEAF);
		put(cx + 2.5, top - 4, LEAF_DARK);
	}

	// Eyes: white disc, dark pupil leaving a thin ring, two catchlights. Blink squashes the height.
	const eyeR = spec.eyes.r * Math.min(pose.scaleX, 1.15);
	const eyeH = eyeR * (1 - pose.blink * 0.85);
	const eyeY = cy + spec.eyes.y * hy;
	for (const side of [-1, 1]) {
		const ex = cx + side * spec.eyes.x * hx;
		if (pose.blink >= 0.95) {
			for (let dx = -eyeR + 1; dx <= eyeR - 1; dx++) put(ex + dx, eyeY, pose.palette.outline);
			continue;
		}
		for (let y = Math.floor(eyeY - eyeR); y <= Math.ceil(eyeY + eyeR); y++) {
			for (let x = Math.floor(ex - eyeR); x <= Math.ceil(ex + eyeR); x++) {
				const du = (x + 0.5 - ex) / eyeR;
				const dv = (y + 0.5 - eyeY) / eyeH;
				if (du * du + dv * dv <= 1) put(x, y, pose.palette.eyeWhite);
			}
		}
		const px = ex + pose.gaze.x * eyeR * 0.4;
		const py = eyeY + pose.gaze.y * eyeH * 0.4;
		const pr = eyeR * 0.6;
		const ph = eyeH * 0.6;
		for (let y = Math.floor(py - pr); y <= Math.ceil(py + pr); y++) {
			for (let x = Math.floor(px - pr); x <= Math.ceil(px + pr); x++) {
				const du = (x + 0.5 - px) / pr;
				const dv = (y + 0.5 - py) / ph;
				if (du * du + dv * dv <= 1) put(x, y, pose.palette.pupil);
			}
		}
		if (eyeH > 1.5) {
			put(px - pr * 0.45, py - ph * 0.45, pose.palette.eyeWhite);
			put(px - pr * 0.45 + 1, py - ph * 0.45, pose.palette.eyeWhite);
			put(px + pr * 0.35, py + ph * 0.3, pose.palette.eyeWhite);
		}
	}

	// Mouth.
	const my = Math.round(cy + spec.mouth.y * hy);
	switch (pose.mouth) {
		case "flat":
			put(cx - 1.5, my, pose.palette.outline);
			put(cx - 0.5, my, pose.palette.outline);
			put(cx + 0.5, my, pose.palette.outline);
			break;
		case "smile":
			put(cx - 2.5, my - 1, pose.palette.outline);
			put(cx - 1.5, my, pose.palette.outline);
			put(cx - 0.5, my, pose.palette.outline);
			put(cx + 0.5, my, pose.palette.outline);
			put(cx + 1.5, my - 1, pose.palette.outline);
			break;
		case "o":
			put(cx - 0.5, my - 1, pose.palette.outline);
			put(cx - 1.5, my, pose.palette.outline);
			put(cx + 0.5, my, pose.palette.outline);
			put(cx - 0.5, my + 1, pose.palette.outline);
			break;
	}

	if (pose.blush) {
		for (const side of [-1, 1]) {
			const bx = cx + side * (spec.eyes.x * hx + eyeR * 0.6);
			put(bx, eyeY + eyeR + 1, BLUSH);
			put(bx + side, eyeY + eyeR + 1, BLUSH);
		}
	}

	for (const p of pose.particles) {
		put(p.x, p.y, p.color);
		if (p.shape === "plus") {
			put(p.x - 1, p.y, p.color);
			put(p.x + 1, p.y, p.color);
			put(p.x, p.y - 1, p.color);
			put(p.x, p.y + 1, p.color);
		}
	}

	return pixels;
}
