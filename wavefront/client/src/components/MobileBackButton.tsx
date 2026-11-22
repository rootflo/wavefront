import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router';

/** Phone-only stand-in for the breadcrumb on detail pages. */
const MobileBackButton = ({ to, label }: { to: string; label: string }) => {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      aria-label={label}
      onClick={() => navigate(to)}
      className="frost-text hover:bg-frost-glass -ml-1 flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full md:hidden"
    >
      <ArrowLeft className="h-5 w-5" />
    </button>
  );
};

export default MobileBackButton;
