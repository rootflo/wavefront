import { Alert, AlertDescription, AlertTitle } from '@app/components/ui/alert';
import { cn } from '@app/lib/utils';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

const alertVariant = {
  error: 'destructive',
  success: 'success',
  info: 'info',
} as const;

type BannerVariant = keyof typeof alertVariant;

const variantIcon = {
  error: AlertCircle,
  success: CheckCircle2,
  info: Info,
} as const;

const variantIconClass = {
  error: 'text-rose-600 dark:text-rose-400',
  success: 'text-emerald-600 dark:text-emerald-400',
  info: 'text-brand',
} as const;

type BannerProps = {
  message: string;
  title?: string;
  onDismiss?: () => void;
  variant?: BannerVariant;
};

const Banner = ({ message, title, onDismiss, variant = 'info' }: BannerProps) => {
  const Icon = variantIcon[variant];

  return (
    <Alert
      variant={alertVariant[variant]}
      className="mb-4 flex shrink-0 items-center gap-3 [&>svg]:static [&>svg]:top-auto [&>svg]:left-auto [&>svg]:translate-y-0 [&>svg~*]:pl-0"
    >
      <Icon className={cn('h-4 w-4 shrink-0', variantIconClass[variant])} aria-hidden />
      <div className="min-w-0 flex-1">
        {title ? <AlertTitle>{title}</AlertTitle> : null}
        <AlertDescription className="break-words">{message}</AlertDescription>
      </div>
      {onDismiss ? (
        <button
          type="button"
          aria-label="Dismiss"
          className="frost-text-muted hover:bg-frost-glass hover:text-frost-text cursor-pointer rounded-md p-0.5"
          onClick={onDismiss}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </Alert>
  );
};

type TypedBannerProps = Omit<BannerProps, 'variant'>;

const ErrorBanner = (props: TypedBannerProps) => <Banner variant="error" {...props} />;
const SuccessBanner = (props: TypedBannerProps) => <Banner variant="success" {...props} />;
const InfoBanner = (props: TypedBannerProps) => <Banner variant="info" {...props} />;

export { Banner, ErrorBanner, SuccessBanner, InfoBanner };
export default Banner;
