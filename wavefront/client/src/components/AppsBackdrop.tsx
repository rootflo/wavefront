interface AppsBackdropProps {
  /** Optional colour that glows from the bottom, used by the apps home page when pointing at a card. */
  glow?: { tint: string; x: number } | null;
  /** Whether this page shows the glow layer at all. */
  withGlow?: boolean;
}

/**
 * The calm background shared by the apps pages: one soft light behind the heading and a faint dot grid that
 * fades down the page. Put it first inside a `relative isolate` container.
 */
const AppsBackdrop = ({ glow, withGlow }: AppsBackdropProps) => (
  <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
    <div className="absolute inset-0 bg-[radial-gradient(60%_70%_at_22%_-10%,rgb(47_109_246/0.2),transparent_70%)] dark:bg-[radial-gradient(60%_70%_at_22%_-10%,rgb(47_109_246/0.26),transparent_70%)]" />
    <div className="absolute inset-0 bg-[radial-gradient(rgb(15_23_42/0.16)_1px,transparent_1.2px)] [mask-image:linear-gradient(180deg,black_0%,transparent_85%)] bg-[length:22px_22px] dark:bg-[radial-gradient(rgb(255_255_255/0.12)_1px,transparent_1.2px)]" />
    {withGlow ? (
      <div
        className="absolute inset-0 transition-[opacity,background] duration-500 ease-out"
        style={{
          opacity: glow ? 1 : 0,
          background: glow
            ? `radial-gradient(45% 55% at ${glow.x}% 90%, rgb(${glow.tint} / 0.38), transparent 70%)`
            : undefined,
        }}
      />
    ) : null}
  </div>
);

export default AppsBackdrop;
