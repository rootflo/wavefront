/**
 * Card colours, as RGB triplets so one tint drives the banner, glow, avatar and buttons. Each is dark enough
 * for white text on a solid fill, and neighbours differ in hue so cards side by side never look alike.
 */
export const APP_TINTS = [
  '47 109 246', // blue
  '139 92 246', // violet
  '20 184 166', // teal
  '244 63 94', // rose
  '234 88 12', // orange
  '22 163 74', // green
];

export const tintFor = (index: number) => APP_TINTS[index % APP_TINTS.length];
