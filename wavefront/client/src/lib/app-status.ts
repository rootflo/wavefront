import dayjs from 'dayjs';

const LIVE_STATUSES = new Set(['active', 'running', 'ready', 'healthy', 'deployed', 'success']);

/** Whether an app's status means it is up, which drives the green light on the app cards. */
export const isLiveStatus = (status: string | null | undefined) => LIVE_STATUSES.has((status ?? '').toLowerCase());

/** "5m ago", "3h ago", "2d ago", "8mo ago": short enough for a narrow tile. */
export const shortAgo = (date: dayjs.Dayjs) => {
  const minutes = dayjs().diff(date, 'minute');
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months}mo ago` : `${Math.floor(months / 12)}y ago`;
};
