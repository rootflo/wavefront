import { TToastType } from '@app/store';
import { ToastErrorIcon, ToastSuccessIcon, ToastWarningIcon } from '@app/assets/icons/toast-icons';
import { useEffect } from 'react';

const iconMap = {
  success: <ToastSuccessIcon />,
  error: <ToastErrorIcon />,
  warning: <ToastWarningIcon />,
};

const Toast = ({
  visible,
  reset,
  type,
  message,
  timeout = 3000,
}: {
  visible: boolean;
  reset: () => void;
  type: TToastType;
  message: string;
  timeout?: number;
}) => {
  useEffect(() => {
    if (visible) {
      const timeoutId = setTimeout(reset, timeout);
      return () => clearTimeout(timeoutId);
    }
  }, [visible, timeout, reset]);

  if (!visible) return <></>;

  return (
    <>
      <div
        className="frost-glass-strong frost-text animate-fade-in border-frost-border ring-frost-border fixed bottom-10 left-1/2 z-[1000] flex w-full max-w-xs -translate-x-1/2 items-center rounded-lg border p-4 shadow-[var(--frost-dialog-shadow)] ring-1 backdrop-blur-xl duration-150"
        role="alert"
      >
        {type && iconMap[type]}
        <div className="ml-3 text-sm font-normal break-all">{message}</div>
        <button
          type="button"
          className="frost-text-muted hover:bg-frost-glass hover:text-frost-text focus:ring-frost-border -mx-1.5 -my-1.5 ml-auto inline-flex h-8 w-8 items-center justify-center rounded-lg p-1.5 focus:ring-2"
          data-dismiss-target="#toast-success"
          aria-label="Close"
          onClick={() => reset()}
        >
          <span className="sr-only">Close</span>
          <svg
            className="h-3 w-3"
            aria-hidden="true"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 14 14"
          >
            <path
              stroke="currentColor"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6"
            />
          </svg>
        </button>
      </div>
    </>
  );
};

export default Toast;
