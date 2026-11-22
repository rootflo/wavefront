import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Kept here because shadcn/ui components import `cn` from @app/lib/utils
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
