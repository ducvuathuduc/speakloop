// Single source of truth for surfaces (Alexa+ MCP Design Guide, Layout and Rendering + Visual Foundations).
// Author everything at the 768x480 base canvas and apply ONE root zoom per device class.
// `deviceClass` from hostContext is authoritative; maxWidth/displayMode is a best-effort fallback.

export const BASE = { width: 768, height: 480 };

export const SURFACES = {
  "echo-show-15": { breakpoint: "hub", zoom: 1280 / 768 },   // 1280x800 -> 1.667
  "echo-show-8": { breakpoint: "hub", zoom: 1280 / 768 },    // 1280x800 -> 1.667
  "echo-show-21": { breakpoint: "hub", zoom: Math.min(1920 / 768, 1080 / 480) }, // 1920x1080 -> 2.25
  "echo-show-5": { breakpoint: "hub-small", zoom: 1 },       // 960x480
  mobile: { breakpoint: "compact", zoom: 1 },
  web: { breakpoint: "web", zoom: 1 },
};

/** Resolve hostContext once to {breakpoint, zoom, warning}. */
export function resolveSurface(ctx = {}) {
  const dc = ctx.deviceClass && String(ctx.deviceClass).toLowerCase();
  if (dc && SURFACES[dc]) return { ...SURFACES[dc], deviceClass: dc };
  if (dc) {
    if (dc.includes("show") || dc.includes("hub")) return { ...SURFACES["echo-show-8"], deviceClass: dc };
    if (dc.includes("mobile") || dc.includes("phone")) return { ...SURFACES.mobile, deviceClass: dc };
  }
  const w = ctx.maxWidth ?? ctx.containerDimensions?.width ?? ctx.containerDimensions?.maxWidth;
  const warning = "hostContext.deviceClass missing; falling back to width heuristics";
  if (ctx.isMobile || ctx.platform === "mobile") return { ...SURFACES.mobile, deviceClass: "mobile", warning };
  if (typeof w === "number") {
    if (w >= 1280) return { ...SURFACES["echo-show-8"], deviceClass: "inferred-hub", warning };
    if (w < BASE.width) return { ...SURFACES.mobile, deviceClass: "inferred-compact", warning };
    return { breakpoint: "web", zoom: Math.min(w / BASE.width, 1280 / 768), deviceClass: "inferred-web", warning };
  }
  return { ...SURFACES.web, deviceClass: "unknown", warning };
}

/** Apply the surface to the root element: one class + one zoom. */
export function applySurface(root, surface, theme) {
  root.dataset.breakpoint = surface.breakpoint;
  root.style.setProperty("--surface-zoom", String(Math.round(surface.zoom * 1000) / 1000));
  if (theme) document.documentElement.dataset.theme = theme;
}
