/** Tinted badge/chip colors that read well in both light and dark mode. */
export type Tone = 'success' | 'warning' | 'info' | 'danger' | 'neutral' | 'violet' | 'emerald';

export const toneClass: Record<Tone, string> = {
  success: 'border-transparent bg-green-500/12 text-green-700 hover:bg-green-500/12 dark:text-green-300',
  warning: 'border-transparent bg-amber-500/14 text-amber-700 hover:bg-amber-500/14 dark:text-amber-300',
  info: 'border-transparent bg-blue-500/12 text-blue-700 hover:bg-blue-500/12 dark:text-blue-300',
  danger: 'border-transparent bg-red-500/12 text-red-700 hover:bg-red-500/12 dark:text-red-300',
  neutral: 'border-transparent bg-slate-500/12 text-slate-700 hover:bg-slate-500/12 dark:text-slate-300',
  violet: 'border-transparent bg-purple-500/12 text-purple-700 hover:bg-purple-500/12 dark:text-purple-300',
  emerald: 'border-transparent bg-emerald-500/12 text-emerald-700 hover:bg-emerald-500/12 dark:text-emerald-300',
};
