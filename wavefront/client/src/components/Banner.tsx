import { Alert, AlertDescription } from '@app/components/ui/alert';
import { X } from 'lucide-react';

const alertVariant = {
  error: 'destructive',
  success: 'success',
  info: 'info',
} as const;

type BannerVariant = keyof typeof alertVariant;

type BannerProps = {
  message: string;
  onDismiss?: () => void;
  variant?: BannerVariant;
};

const Banner = ({ message, onDismiss, variant = 'info' }: BannerProps) => (
  <Alert variant={alertVariant[variant]} className="mb-4 flex shrink-0 items-start gap-3">
    <AlertDescription className="min-w-0 flex-1 break-words">{message}</AlertDescription>
    {onDismiss ? (
      <button
        type="button"
        aria-label="Dismiss"
        className="cursor-pointer rounded-md p-0.5 hover:bg-black/5"
        onClick={onDismiss}
      >
        <X className="h-4 w-4" />
      </button>
    ) : null}
  </Alert>
);

type TypedBannerProps = Omit<BannerProps, 'variant'>;

const ErrorBanner = (props: TypedBannerProps) => <Banner variant="error" {...props} />;
const SuccessBanner = (props: TypedBannerProps) => <Banner variant="success" {...props} />;
const InfoBanner = (props: TypedBannerProps) => <Banner variant="info" {...props} />;

export { Banner, ErrorBanner, SuccessBanner, InfoBanner };
export default Banner;
