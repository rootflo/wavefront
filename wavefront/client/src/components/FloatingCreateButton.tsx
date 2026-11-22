import { Plus } from 'lucide-react';
import React from 'react';

interface FloatingCreateButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  icon?: React.ComponentType<{ className?: string; strokeWidth?: number }>;
}

/** Phone-only "create" pill pinned to the bottom-right of the screen; larger screens use the page's own button. */
const FloatingCreateButton = ({ label, onClick, disabled, icon: Icon = Plus }: FloatingCreateButtonProps) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className="bg-brand hover:bg-brand-hover fixed right-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-20 inline-flex cursor-pointer items-center gap-1.5 rounded-full px-4 py-3 text-[13.5px] font-semibold text-white shadow-lg shadow-black/25 transition-colors disabled:cursor-not-allowed disabled:opacity-60 sm:hidden"
  >
    <Icon className="size-4" strokeWidth={2.4} />
    {label}
  </button>
);

export default FloatingCreateButton;
