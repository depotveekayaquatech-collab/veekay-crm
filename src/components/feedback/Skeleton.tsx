export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-border/60 ${className}`} />;
}

/** Full-page loading state — shown while session restore or a protected
 * route's auth check is in flight, so refresh never flashes a blank
 * white screen (spec section 22: never show a blank screen while
 * data loads). */
export function FullPageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-subtle">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
        <p className="text-sm text-gray-500">Loading your workspace…</p>
      </div>
    </div>
  );
}
