import { useThemeStore } from '@app/store/theme-store';
import { Moon, Sun } from 'lucide-react';
import { cn } from '@app/lib/utils';

const ThemeToggle = () => {
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const isDark = theme === 'dark';

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      onClick={toggleTheme}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={cn(
        'group border-frost-border relative inline-flex h-8 w-[3.75rem] shrink-0 cursor-pointer items-center rounded-full border p-0.5',
        'ring-frost-border shadow-[var(--frost-inset-shadow)] ring-1 transition-colors duration-300',
        'focus-visible:ring-brand/40 focus-visible:ring-2 focus-visible:outline-none',
        isDark
          ? 'bg-[linear-gradient(135deg,#1e293b_0%,#0f172a_55%,#312e81_100%)]'
          : 'bg-[linear-gradient(135deg,#fff7ed_0%,#e0f2fe_50%,#dbeafe_100%)]'
      )}
    >
      {/* Sun side */}
      <span
        className={cn(
          'absolute left-1.5 z-[1] flex h-5 w-5 items-center justify-center transition-all duration-300',
          isDark ? 'scale-90 text-slate-500 opacity-50' : 'scale-100 text-amber-500 opacity-100'
        )}
        aria-hidden
      >
        <Sun className="h-3.5 w-3.5" strokeWidth={2.25} />
      </span>

      {/* Moon side */}
      <span
        className={cn(
          'absolute right-1.5 z-[1] flex h-5 w-5 items-center justify-center transition-all duration-300',
          isDark ? 'scale-100 text-indigo-200 opacity-100' : 'scale-90 text-slate-400 opacity-50'
        )}
        aria-hidden
      >
        <Moon className="h-3.5 w-3.5" strokeWidth={2.25} />
      </span>

      {/* Sliding knob */}
      <span
        className={cn(
          'relative z-[2] flex h-6 w-6 items-center justify-center rounded-full transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)]',
          'shadow-[0_2px_8px_-2px_rgba(15,23,42,0.35),0_1px_0_rgba(255,255,255,0.45)_inset]',
          isDark
            ? 'translate-x-[1.7rem] bg-[linear-gradient(145deg,#e2e8f0_0%,#94a3b8_100%)] text-slate-800'
            : 'translate-x-0 bg-[linear-gradient(145deg,#ffffff_0%,#fef3c7_100%)] text-amber-500'
        )}
      >
        {isDark ? <Moon className="h-3 w-3" strokeWidth={2.5} /> : <Sun className="h-3 w-3" strokeWidth={2.5} />}
      </span>
    </button>
  );
};

export default ThemeToggle;
