import { cn } from '@app/lib/utils';
import { LayoutGrid } from 'lucide-react';
import React, { useLayoutEffect, useRef, useState } from 'react';

interface ColumnsToggleProps {
  value: number;
  choices: readonly number[];
  onChange: (value: number) => void;
  className?: string;
}

// Width of one number. The toggle is as wide as the search box beside it, so only a few numbers fit at once.
const SEGMENT = 36;
// Near either edge the strip is already scrolled all the way, so the end numbers are easy to land on.
const EDGE = 0.15;

/**
 * Cards per row as a strip of numbers with a knob that slides to the chosen one. Only the numbers around the
 * choice show; moving the mouse towards either end slides the strip that way, and leaving recentres it.
 * Arrow keys step through it.
 */
const ColumnsToggle: React.FC<ColumnsToggleProps> = ({ value, choices, onChange, className }) => {
  const buttonsRef = useRef<(HTMLButtonElement | null)[]>([]);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [hoverOffset, setHoverOffset] = useState<number | null>(null);
  const index = Math.max(0, choices.indexOf(value));

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const observer = new ResizeObserver(() => setViewportWidth(viewport.clientWidth));
    observer.observe(viewport);
    setViewportWidth(viewport.clientWidth);
    return () => observer.disconnect();
  }, []);

  const maxOffset = Math.max(0, choices.length * SEGMENT - viewportWidth);
  const centred = Math.min(maxOffset, Math.max(0, index * SEGMENT + SEGMENT / 2 - viewportWidth / 2));
  const offset = hoverOffset ?? centred;

  const select = (next: number) => {
    const clamped = Math.min(choices.length - 1, Math.max(0, next));
    setHoverOffset(null);
    onChange(choices[clamped]);
    buttonsRef.current[clamped]?.focus({ preventScroll: true });
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    const step = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[event.key];
    if (step !== undefined) {
      event.preventDefault();
      select(index + step);
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      select(event.key === 'Home' ? 0 : choices.length - 1);
    }
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== 'mouse' || maxOffset === 0) return;
    const box = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - box.left) / box.width;
    setHoverOffset(Math.min(1, Math.max(0, (ratio - EDGE) / (1 - 2 * EDGE))) * maxOffset);
  };

  // Fade whichever end still has numbers hidden past it.
  const fadeLeft = offset > 1;
  const fadeRight = offset < maxOffset - 1;
  const mask = `linear-gradient(to right, ${fadeLeft ? 'transparent, #000 16px' : '#000'}, ${fadeRight ? '#000 calc(100% - 16px), transparent' : '#000'})`;

  return (
    <div
      className={cn(
        'frost-control ring-frost-border inline-flex h-10 w-48 shrink-0 items-center gap-2.5 rounded-xl border pr-1 pl-3.5 ring-1',
        className
      )}
      title="Cards per row"
    >
      <LayoutGrid className="frost-text-subtle size-4 shrink-0" aria-hidden />
      <div
        ref={viewportRef}
        className="min-w-0 flex-1 overflow-hidden"
        style={{ maskImage: mask, WebkitMaskImage: mask }}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHoverOffset(null)}
      >
        <div
          role="radiogroup"
          aria-label="Cards per row"
          className="relative flex w-max transition-transform duration-300 ease-out motion-reduce:transition-none"
          style={{ transform: `translateX(${-offset}px)` }}
          onKeyDown={onKeyDown}
        >
          <span
            aria-hidden
            className="bg-brand absolute inset-y-0 left-0 rounded-lg shadow-[0_6px_14px_-6px_var(--color-brand)] transition-transform duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] motion-reduce:transition-none"
            style={{ width: SEGMENT, transform: `translateX(${index * SEGMENT}px)` }}
          />
          {choices.map((choice, i) => (
            <button
              key={choice}
              ref={(el) => {
                buttonsRef.current[i] = el;
              }}
              type="button"
              role="radio"
              aria-checked={i === index}
              aria-label={`${choice} per row`}
              tabIndex={i === index ? 0 : -1}
              onClick={() => onChange(choice)}
              style={{ width: SEGMENT }}
              className={cn(
                'relative z-[1] flex h-8 shrink-0 cursor-pointer items-center justify-center rounded-lg text-[13px] font-semibold tabular-nums transition-colors duration-200',
                'focus-visible:ring-brand/40 focus-visible:ring-2 focus-visible:outline-none focus-visible:ring-inset',
                i === index ? 'text-white' : 'frost-text-muted hover:text-frost-text'
              )}
            >
              {choice}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ColumnsToggle;
