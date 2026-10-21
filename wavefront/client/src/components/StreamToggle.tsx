import { Label } from '@app/components/ui/label';
import { Switch } from '@app/components/ui/switch';
import clsx from 'clsx';
import { Zap } from 'lucide-react';
import React from 'react';

interface StreamToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  /** What the run produces, as the hints name it: 'reply', 'result', ... */
  subject?: string;
  /**
   * What streaming gives you here, when the default is wrong. A workflow
   * streams its steps rather than text, so it says so.
   */
  liveHint?: string;
}

/**
 * Whether a run streams, as a header control.
 *
 * Icon, label, current behaviour and switch live in one chip so they read as
 * a single control - a label on the left of a full-width row and a switch on
 * the right end up a screen apart and stop looking related. The second line
 * says what the setting does right now, so the state is legible without
 * hovering for a tooltip or running something to find out.
 *
 * Sized `h-9` to line up with the outline buttons it sits beside.
 */
const StreamToggle: React.FC<StreamToggleProps> = ({ enabled, onChange, subject = 'response', liveHint }) => (
  <Label
    htmlFor="stream-toggle"
    title={
      enabled
        ? `The ${subject} is written out word by word, with each run step as it happens`
        : `The ${subject} appears once the run finishes`
    }
    className="frost-control ring-frost-border flex h-9 cursor-pointer items-center gap-2 rounded-md px-3 ring-1 transition-colors"
  >
    <Zap className={clsx('h-4 w-4 shrink-0', enabled ? 'text-brand' : 'frost-text-subtle')} />
    <span className="flex flex-col justify-center gap-0.5">
      <span className="frost-text text-xs leading-none font-medium">Stream</span>
      <span className="frost-text-subtle text-[10px] leading-none">
        {enabled ? (liveHint ?? 'Writes out word by word') : `Waits for the full ${subject}`}
      </span>
    </span>
    <Switch id="stream-toggle" checked={enabled} onCheckedChange={onChange} />
  </Label>
);

export default StreamToggle;
