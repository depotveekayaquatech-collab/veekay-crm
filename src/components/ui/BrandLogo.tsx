/**
 * The WaTR logo (public/watr-logo.png, transparent). It is maroon and gold, so on a dark surface
 * (the sidebar, the sign-in side panel) use `tile` to sit it on a white rounded tile.
 */
export function BrandLogo({ height = 36, tile = false, className = "" }: { height?: number; tile?: boolean; className?: string }) {
  const img = (
    <img
      src="/watr-logo.png"
      alt="WaTR"
      style={{ height }}
      className={`block w-auto max-w-none select-none ${tile ? "" : className}`}
      draggable={false}
    />
  );
  if (!tile) return img;
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-xl bg-white px-2.5 py-1.5 shadow-sm ring-1 ring-black/5 ${className}`}>
      {img}
    </span>
  );
}
