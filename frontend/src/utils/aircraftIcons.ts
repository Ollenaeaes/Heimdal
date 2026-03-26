/**
 * Aircraft icon generation for MapLibre.
 *
 * Six icon types — bold top-down silhouettes designed to be readable at 32px.
 * All icons point north (0°). MapLibre rotates via icon-rotate using track heading.
 */

const ICON_SIZE = 32;
const S = ICON_SIZE; // shorthand

interface MapImage {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

// ----- Type code → icon category mapping -----

const FIGHTER_TYPES = new Set([
  'F18H', 'F16', 'SB39', 'JAS39', 'SB05', 'EF20', 'F35',
]);

const HELICOPTER_TYPES = new Set([
  'EH10', 'H60', 'NH90', 'AS32', 'EC25', 'EC35', 'EC45', 'EC55',
  'EC75', 'B429', 'A169', 'AS50', 'B505', 'B412', 'S70', 'H160',
  'AW13', 'AW16', 'AW18', 'S76',
]);

const SMALL_PROP_TYPES = new Set([
  'D228', 'BN2P', 'DHC6', 'MF17', 'G115', 'G120', 'G12T', 'PC12',
  'AN28', 'M28', 'FA20', 'SBR1',
]);

const LARGE_PROP_TYPES = new Set([
  'C30J', 'C130', 'C295', 'P3', 'DH8C', 'SF34', 'F27',
]);

const LARGE_JET_TYPES = new Set([
  'P8', 'P8A', 'E3CF', 'E3TF', 'R135', 'RC35', 'E6', 'B737', 'B707',
]);

export function getIconCategory(typeCode: string | null | undefined): string {
  if (!typeCode) return 'small_jet';
  const t = typeCode.toUpperCase();
  if (FIGHTER_TYPES.has(t)) return 'fighter';
  if (HELICOPTER_TYPES.has(t)) return 'helicopter';
  if (SMALL_PROP_TYPES.has(t)) return 'small_prop';
  if (LARGE_PROP_TYPES.has(t)) return 'large_prop';
  if (LARGE_JET_TYPES.has(t)) return 'large_jet';
  return 'small_jet';
}

// ----- Drawing helpers -----

function createCtx(): CanvasRenderingContext2D {
  const canvas = document.createElement('canvas');
  canvas.width = S;
  canvas.height = S;
  return canvas.getContext('2d')!;
}

function finish(ctx: CanvasRenderingContext2D, color: string): MapImage {
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 1;
  ctx.stroke();
  const imageData = ctx.getImageData(0, 0, S, S);
  return { width: S, height: S, data: imageData.data };
}

const cx = S / 2; // center x

// ----- Icon shapes (all point north / up) -----

/** Fighter — delta-wing, aggressive swept shape */
function drawFighter(color: string): MapImage {
  const ctx = createCtx();
  ctx.beginPath();
  // Nose
  ctx.moveTo(cx, 2);
  // Right fuselage down to wing root
  ctx.lineTo(cx + 2, S * 0.4);
  // Right wingtip (far out, swept back)
  ctx.lineTo(S - 2, S * 0.7);
  // Back to fuselage
  ctx.lineTo(cx + 2.5, S * 0.65);
  // Right tail fin
  ctx.lineTo(cx + 5, S - 3);
  // Tail center
  ctx.lineTo(cx, S - 5);
  // Left tail fin
  ctx.lineTo(cx - 5, S - 3);
  // Back to fuselage
  ctx.lineTo(cx - 2.5, S * 0.65);
  // Left wingtip
  ctx.lineTo(2, S * 0.7);
  // Left fuselage
  ctx.lineTo(cx - 2, S * 0.4);
  ctx.closePath();
  return finish(ctx, color);
}

/** Helicopter — teardrop body + landing skids + tail boom with rotor indicator */
function drawHelicopter(color: string): MapImage {
  const ctx = createCtx();

  // Main body — rounded teardrop
  ctx.beginPath();
  ctx.moveTo(cx, 4);           // nose
  ctx.quadraticCurveTo(cx + 7, 6, cx + 6, 13);  // right front curve
  ctx.lineTo(cx + 4, 17);      // right body
  ctx.lineTo(cx + 1.5, 18);    // narrow to tail boom
  ctx.lineTo(cx + 1.5, S - 4); // tail boom right
  ctx.lineTo(cx + 5, S - 3);   // tail rotor right
  ctx.lineTo(cx + 5, S - 1);   // tail rotor right end
  ctx.lineTo(cx - 5, S - 1);   // tail rotor left end
  ctx.lineTo(cx - 5, S - 3);   // tail rotor left
  ctx.lineTo(cx - 1.5, S - 4); // tail boom left
  ctx.lineTo(cx - 1.5, 18);    // narrow to body
  ctx.lineTo(cx - 4, 17);      // left body
  ctx.lineTo(cx - 6, 13);      // left front
  ctx.quadraticCurveTo(cx - 7, 6, cx, 4);  // left front curve
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Landing skids
  ctx.beginPath();
  ctx.moveTo(cx - 8, 10);
  ctx.lineTo(cx - 8, 19);
  ctx.moveTo(cx + 8, 10);
  ctx.lineTo(cx + 8, 19);
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Rotor mast dot
  ctx.beginPath();
  ctx.arc(cx, 11, 2, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.fill();

  const imageData = ctx.getImageData(0, 0, S, S);
  return { width: S, height: S, data: imageData.data };
}

/** Small prop — straight high-wing, narrow body */
function drawSmallProp(color: string): MapImage {
  const ctx = createCtx();
  ctx.beginPath();
  // Nose
  ctx.moveTo(cx, 3);
  // Right fuselage
  ctx.lineTo(cx + 2, S * 0.25);
  // Right wing (straight, full span)
  ctx.lineTo(S - 2, S * 0.38);
  ctx.lineTo(S - 2, S * 0.44);
  // Back to fuselage
  ctx.lineTo(cx + 2, S * 0.44);
  // Down to tail
  ctx.lineTo(cx + 2, S * 0.78);
  // Right tailplane
  ctx.lineTo(cx + 7, S * 0.84);
  ctx.lineTo(cx + 7, S * 0.88);
  ctx.lineTo(cx + 2, S * 0.86);
  // Tail
  ctx.lineTo(cx, S - 2);
  // Left tail
  ctx.lineTo(cx - 2, S * 0.86);
  ctx.lineTo(cx - 7, S * 0.88);
  ctx.lineTo(cx - 7, S * 0.84);
  ctx.lineTo(cx - 2, S * 0.78);
  // Left fuselage
  ctx.lineTo(cx - 2, S * 0.44);
  // Left wing
  ctx.lineTo(2, S * 0.44);
  ctx.lineTo(2, S * 0.38);
  ctx.lineTo(cx - 2, S * 0.25);
  ctx.closePath();
  return finish(ctx, color);
}

/** Large turboprop — wider body, thick straight wings, 4-engine bumps */
function drawLargeProp(color: string): MapImage {
  const ctx = createCtx();
  ctx.beginPath();
  // Nose (rounded)
  ctx.moveTo(cx, 2);
  ctx.lineTo(cx + 3, S * 0.2);
  // Right wing
  ctx.lineTo(S - 1, S * 0.38);
  ctx.lineTo(S - 1, S * 0.46);
  ctx.lineTo(cx + 3, S * 0.44);
  // Down to tail
  ctx.lineTo(cx + 3, S * 0.76);
  // Right tailplane
  ctx.lineTo(cx + 8, S * 0.83);
  ctx.lineTo(cx + 8, S * 0.88);
  ctx.lineTo(cx + 3, S * 0.85);
  // Tail
  ctx.lineTo(cx, S - 1);
  // Left
  ctx.lineTo(cx - 3, S * 0.85);
  ctx.lineTo(cx - 8, S * 0.88);
  ctx.lineTo(cx - 8, S * 0.83);
  ctx.lineTo(cx - 3, S * 0.76);
  ctx.lineTo(cx - 3, S * 0.44);
  ctx.lineTo(1, S * 0.46);
  ctx.lineTo(1, S * 0.38);
  ctx.lineTo(cx - 3, S * 0.2);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Engine nacelles (4 ovals on wings)
  ctx.fillStyle = color;
  ctx.strokeStyle = 'rgba(0,0,0,0.4)';
  ctx.lineWidth = 0.8;
  for (const xOff of [-9, -5, 5, 9]) {
    ctx.beginPath();
    ctx.ellipse(cx + xOff, S * 0.40, 1.5, 3, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  const imageData = ctx.getImageData(0, 0, S, S);
  return { width: S, height: S, data: imageData.data };
}

/** Small jet — swept wings, T-tail, narrow body */
function drawSmallJet(color: string): MapImage {
  const ctx = createCtx();
  ctx.beginPath();
  // Nose
  ctx.moveTo(cx, 2);
  ctx.lineTo(cx + 1.5, S * 0.3);
  // Right swept wing
  ctx.lineTo(S - 3, S * 0.55);
  ctx.lineTo(S - 4, S * 0.6);
  ctx.lineTo(cx + 2, S * 0.5);
  // Down to tail
  ctx.lineTo(cx + 2, S * 0.78);
  // Right T-tail
  ctx.lineTo(cx + 6, S * 0.85);
  ctx.lineTo(cx + 5.5, S * 0.9);
  ctx.lineTo(cx + 2, S * 0.86);
  ctx.lineTo(cx, S - 2);
  // Left
  ctx.lineTo(cx - 2, S * 0.86);
  ctx.lineTo(cx - 5.5, S * 0.9);
  ctx.lineTo(cx - 6, S * 0.85);
  ctx.lineTo(cx - 2, S * 0.78);
  ctx.lineTo(cx - 2, S * 0.5);
  ctx.lineTo(4, S * 0.6);
  ctx.lineTo(3, S * 0.55);
  ctx.lineTo(cx - 1.5, S * 0.3);
  ctx.closePath();
  return finish(ctx, color);
}

/** Large jet — wide body, swept wings, 2 engine pods, big tail */
function drawLargeJet(color: string): MapImage {
  const ctx = createCtx();
  ctx.beginPath();
  // Nose
  ctx.moveTo(cx, 1);
  ctx.lineTo(cx + 3, S * 0.22);
  // Right swept wing
  ctx.lineTo(S - 1, S * 0.52);
  ctx.lineTo(S - 2, S * 0.58);
  ctx.lineTo(cx + 3, S * 0.48);
  // Down to tail
  ctx.lineTo(cx + 3, S * 0.74);
  // Right tailplane
  ctx.lineTo(cx + 9, S * 0.84);
  ctx.lineTo(cx + 8, S * 0.89);
  ctx.lineTo(cx + 3, S * 0.84);
  ctx.lineTo(cx, S - 1);
  // Left
  ctx.lineTo(cx - 3, S * 0.84);
  ctx.lineTo(cx - 8, S * 0.89);
  ctx.lineTo(cx - 9, S * 0.84);
  ctx.lineTo(cx - 3, S * 0.74);
  ctx.lineTo(cx - 3, S * 0.48);
  ctx.lineTo(2, S * 0.58);
  ctx.lineTo(1, S * 0.52);
  ctx.lineTo(cx - 3, S * 0.22);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Engine pods (2, under wings)
  ctx.fillStyle = color;
  ctx.strokeStyle = 'rgba(0,0,0,0.4)';
  ctx.lineWidth = 0.8;
  for (const xOff of [-7, 7]) {
    ctx.beginPath();
    ctx.ellipse(cx + xOff, S * 0.48, 1.8, 3.5, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }

  const imageData = ctx.getImageData(0, 0, S, S);
  return { width: S, height: S, data: imageData.data };
}

// ----- Icon registry -----

const CATEGORY_COLORS: Record<string, string> = {
  military: '#f59e0b',
  coast_guard: '#06b6d4',
  police: '#3b82f6',
  government: '#8b5cf6',
};

const DRAW_FUNCTIONS: Record<string, (color: string) => MapImage> = {
  fighter: drawFighter,
  helicopter: drawHelicopter,
  small_prop: drawSmallProp,
  large_prop: drawLargeProp,
  small_jet: drawSmallJet,
  large_jet: drawLargeJet,
};

/**
 * Register all aircraft icons on a MapLibre map instance.
 * Icon names: `ac-{iconType}-{category}` e.g. `ac-fighter-military`
 */
export function registerAircraftIcons(map: maplibregl.Map) {
  for (const [iconType, drawFn] of Object.entries(DRAW_FUNCTIONS)) {
    for (const [category, color] of Object.entries(CATEGORY_COLORS)) {
      const name = `ac-${iconType}-${category}`;
      if (!map.hasImage(name)) {
        map.addImage(name, drawFn(color), { sdf: false });
      }
    }
    // Default gray for unknown category
    const defaultName = `ac-${iconType}-default`;
    if (!map.hasImage(defaultName)) {
      map.addImage(defaultName, drawFn('#9ca3af'), { sdf: false });
    }
  }
}

/** MapLibre expression for icon-image based on properties. */
export function buildIconImageExpression(): maplibregl.ExpressionSpecification {
  return [
    'concat',
    'ac-',
    ['get', 'icon_type'],
    '-',
    ['coalesce', ['get', 'category'], 'default'],
  ];
}
