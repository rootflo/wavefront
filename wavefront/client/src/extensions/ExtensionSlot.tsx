import { ExtensionBoundary } from './ExtensionBoundary';
import { useSlotContributions } from './registry';
import type { SlotName, SlotProps } from './types';

interface Props {
  name: SlotName;
  props?: SlotProps;
  /** Wraps the contributions; not rendered when the slot is empty. */
  className?: string;
}

/** Renders what remotes registered for `name`; nothing at all in a console without remotes. */
export function ExtensionSlot({ name, props = {}, className }: Props) {
  const contributions = useSlotContributions(name);
  if (contributions.length === 0) return null;
  return (
    <div className={className} data-extension-slot={name}>
      {contributions.map(({ source, value: Contribution }, index) => (
        <ExtensionBoundary key={`${source}-${index}`} source={source}>
          <Contribution {...props} />
        </ExtensionBoundary>
      ))}
    </div>
  );
}
