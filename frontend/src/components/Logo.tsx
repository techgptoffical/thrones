/** The Thrones mark: three pillars on a base — a seat, a crown, a signal. */
export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="9.5" width="3.4" height="8" rx="1.1" fill="currentColor" />
      <rect x="10.3" y="3.5" width="3.4" height="14" rx="1.1" fill="var(--accent-solid)" />
      <rect x="17.1" y="9.5" width="3.4" height="8" rx="1.1" fill="currentColor" />
      <rect x="3.5" y="19" width="17" height="2.2" rx="1.1" fill="currentColor" />
    </svg>
  );
}
