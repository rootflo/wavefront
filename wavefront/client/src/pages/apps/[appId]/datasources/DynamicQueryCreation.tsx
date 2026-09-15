import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { popupCodeMirrorExtensions } from '@app/lib/code-mirror';
import { validateDynamicQueryYaml } from '@app/lib/utils';
import { langs } from '@uiw/codemirror-extensions-langs';
import CodeMirror from '@uiw/react-codemirror';
import clsx from 'clsx';
import { useEffect, useState } from 'react';

interface DynamicQueryCreationProps {
  queryContent: string;
  setQueryContent: React.Dispatch<React.SetStateAction<string>>;
  isOpen: boolean;
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
  onCreate: () => Promise<void>;
}

const DynamicQueryCreation: React.FC<DynamicQueryCreationProps> = ({
  queryContent,
  setQueryContent,
  isOpen,
  setIsOpen,
  onCreate,
}) => {
  const [error, setError] = useState<string>('');
  const [isCreating, setIsCreating] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) {
      setIsCreating(false);
      setError('');
    }
  }, [isOpen]);

  const handleSubmit = async (content: string) => {
    const response: { valid: boolean; error: string } = validateDynamicQueryYaml(content);
    if (!response.valid) {
      setError(response.error);
      return;
    }

    setError('');
    setIsCreating(true);
    try {
      await onCreate();
    } finally {
      setIsCreating(false);
    }
  };
  const handleClose = () => {
    setQueryContent('');
    setIsOpen(false);
    setError('');
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && !isCreating) {
      handleClose();
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] w-full max-w-[800px] min-w-0 overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Dynamic Query</DialogTitle>
          <DialogDescription>Define your dynamic query configuration for this datasource.</DialogDescription>
        </DialogHeader>

        <div className="flex min-w-0 flex-col gap-3">
          <CodeMirror
            className="w-full min-w-0 rounded-xl border border-[#EFF0F1] bg-white p-4 font-mono text-sm font-normal text-[#282828] outline-none"
            value={queryContent}
            height="500px"
            width="100%"
            maxWidth="100%"
            extensions={[langs.yaml(), ...popupCodeMirrorExtensions]}
            onChange={(value: string) => setQueryContent(value)}
            theme="dark"
          />
        </div>

        <p
          className={clsx(
            'min-h-4 text-sm text-red-500 transition-opacity duration-200',
            error ? 'opacity-100' : 'opacity-0'
          )}
        >
          {error}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isCreating}>
            Cancel
          </Button>
          <Button onClick={() => handleSubmit(queryContent)} disabled={isCreating} loading={isCreating}>
            {isCreating ? 'Creating...' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
export default DynamicQueryCreation;
