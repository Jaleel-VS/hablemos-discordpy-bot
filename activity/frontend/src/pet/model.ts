// Critters: the species catalogue and everything derived from a profile that the rasterizer needs.
// Pure data; no DOM. A species is a body shape plus anchor points. Accessories (later) attach to
// the anchors, so any accessory fits any species.

export const SPECIES = ["blob", "drop", "orb", "sprout", "ghost", "bun", "star", "mochi", "cube", "pebble"] as const;
export type Species = (typeof SPECIES)[number];

export const SPECIES_NAMES: Record<Species, string> = {
	blob: "Blob",
	drop: "Drop",
	orb: "Orb",
	sprout: "Sprout",
	ghost: "Ghost",
	bun: "Bun",
	star: "Star",
	mochi: "Mochi",
	cube: "Cube",
	pebble: "Pebble",
};

/** Drawing grid, in critter pixels. Displayed at integer multiples so pixels stay crisp. */
export const GRID = 40;
/** Every species stands on this row (its shadow's first row), leaving the tallest species room to hop. */
export const GROUND_Y = GRID - 4;
/** Rest-pose top row of a species' body. */
export function bodyTop(species: Species): number {
	return GROUND_Y - 2 * SPECIES_SPECS[species].half.y;
}

/**
 * Anchors are in body space: x in [-1, 1] across the body's width, y in [-1, 1] from top to bottom.
 * `eyes` places the two eyes (mirrored at ±x); `hat` is where headwear sits; `mouth` is below the eyes.
 */
export type SpeciesSpec = {
	/** Body half-extents in grid pixels at rest. */
	half: { x: number; y: number };
	eyes: { x: number; y: number; r: number };
	mouth: { y: number };
	hat: { y: number };
};

export const SPECIES_SPECS: Record<Species, SpeciesSpec> = {
	blob: { half: { x: 15, y: 11 }, eyes: { x: 0.36, y: 0.05, r: 3.6 }, mouth: { y: 0.5 }, hat: { y: -1 } },
	drop: { half: { x: 11, y: 14 }, eyes: { x: 0.36, y: 0.3, r: 3.1 }, mouth: { y: 0.62 }, hat: { y: -1 } },
	orb: { half: { x: 13, y: 13 }, eyes: { x: 0.34, y: 0, r: 3.4 }, mouth: { y: 0.42 }, hat: { y: -1 } },
	sprout: { half: { x: 12, y: 11 }, eyes: { x: 0.36, y: 0.05, r: 3.2 }, mouth: { y: 0.5 }, hat: { y: -1 } },
	ghost: { half: { x: 12, y: 14 }, eyes: { x: 0.34, y: -0.2, r: 3.2 }, mouth: { y: 0.2 }, hat: { y: -1 } },
	bun: { half: { x: 14, y: 11 }, eyes: { x: 0.34, y: 0.1, r: 3.2 }, mouth: { y: 0.55 }, hat: { y: -0.75 } },
	star: { half: { x: 15, y: 15 }, eyes: { x: 0.26, y: 0.05, r: 3 }, mouth: { y: 0.38 }, hat: { y: -0.6 } },
	mochi: { half: { x: 14, y: 10 }, eyes: { x: 0.36, y: 0, r: 3.4 }, mouth: { y: 0.5 }, hat: { y: -1 } },
	cube: { half: { x: 12, y: 12 }, eyes: { x: 0.38, y: -0.05, r: 3.2 }, mouth: { y: 0.42 }, hat: { y: -1 } },
	pebble: { half: { x: 15, y: 10 }, eyes: { x: 0.3, y: 0, r: 3.2 }, mouth: { y: 0.5 }, hat: { y: -0.9 } },
};

// ---- colour -------------------------------------------------------------------------------

export type Rgb = readonly [number, number, number];

/** Shading bands from darkest to lightest, plus fixed eye colours. */
export type Palette = {
	outline: Rgb;
	dark: Rgb;
	shade: Rgb;
	base: Rgb;
	light: Rgb;
	highlight: Rgb;
	eyeWhite: Rgb;
	pupil: Rgb;
};

export function hexToRgb(hex: string): Rgb {
	const n = Number.parseInt(hex.slice(1), 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHsl([r, g, b]: Rgb): [number, number, number] {
	const rn = r / 255;
	const gn = g / 255;
	const bn = b / 255;
	const max = Math.max(rn, gn, bn);
	const min = Math.min(rn, gn, bn);
	const l = (max + min) / 2;
	if (max === min) return [0, 0, l];
	const d = max - min;
	const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
	let h: number;
	if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
	else if (max === gn) h = (bn - rn) / d + 2;
	else h = (rn - gn) / d + 4;
	return [h / 6, s, l];
}

function hslToRgb(h: number, s: number, l: number): Rgb {
	const hue = ((h % 1) + 1) % 1;
	const channel = (n: number): number => {
		const k = (n + hue * 12) % 12;
		const a = s * Math.min(l, 1 - l);
		return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))));
	};
	return [channel(0), channel(8), channel(4)];
}

/** Clamp to the unit interval; shared by palette math and the animator. */
export function clamp01(value: number): number {
	return Math.min(1, Math.max(0, value));
}

/** Hue, saturation and lightness offsets from the base colour for one shading band. */
type BandShift = readonly [dh: number, ds: number, dl: number];

// Shadows shift toward blue-violet and desaturate less; highlights shift warm and wash out, like hand-picked pixel-art ramps.
const BAND_SHIFTS: Record<Exclude<keyof Palette, "eyeWhite" | "pupil">, BandShift> = {
	outline: [0.06, 0.05, -0.42],
	dark: [0.045, 0.05, -0.26],
	shade: [0.025, 0.03, -0.13],
	base: [0, 0, 0],
	light: [-0.015, -0.05, 0.12],
	highlight: [-0.03, -0.15, 0.3],
};

/** Six shading bands from one colour. */
export function paletteFor(hex: string): Palette {
	const [h, s, l] = rgbToHsl(hexToRgb(hex));
	const shifted = ([dh, ds, dl]: BandShift): Rgb => hslToRgb(h + dh, clamp01(s + ds), clamp01(l + dl));
	return {
		outline: shifted(BAND_SHIFTS.outline),
		dark: shifted(BAND_SHIFTS.dark),
		shade: shifted(BAND_SHIFTS.shade),
		base: shifted(BAND_SHIFTS.base),
		light: shifted(BAND_SHIFTS.light),
		highlight: shifted(BAND_SHIFTS.highlight),
		eyeWhite: [246, 247, 255],
		pupil: [27, 26, 46],
	};
}
