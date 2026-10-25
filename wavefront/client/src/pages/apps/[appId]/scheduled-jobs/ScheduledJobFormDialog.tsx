import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { FORM_TAB, isFormTab } from '@app/constants/scheduled-job';
import { ScheduledJob } from '@app/types/scheduled-job';
import { useScheduledJobForm } from './useScheduledJobForm';
import JobSetupTab from './JobSetupTab';
import QueriesTab from './QueriesTab';
import EmailTab from './EmailTab';

interface ScheduledJobFormDialogProps {
  isOpen: boolean;
  appId: string;
  job?: ScheduledJob | null;
  onOpenChange: (open: boolean) => void;
}

const ScheduledJobFormDialog: React.FC<ScheduledJobFormDialogProps> = ({ isOpen, appId, job, onOpenChange }) => {
  const form = useScheduledJobForm({ isOpen, appId, job, onOpenChange });
  const { isEditing, activeTab, setActiveTab, saving, error, handleOpenChange, handleSave } = form;

  return (
    <Dialog open={isOpen} onOpenChange={handleOpenChange}>
      <DialogContent className="flex h-[760px] max-h-[calc(100vh-2rem)] max-w-4xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>{isEditing ? 'Edit Scheduled Job' : 'Create Scheduled Job'}</DialogTitle>
          <DialogDescription>
            Schedule one or more dynamic query reports to be emailed on a cron schedule.
          </DialogDescription>
        </DialogHeader>

        <Tabs
          value={activeTab}
          onValueChange={(value) => {
            if (isFormTab(value)) setActiveTab(value);
          }}
          className="flex min-h-0 flex-1 flex-col overflow-hidden"
        >
          <TabsList className="grid w-full shrink-0 grid-cols-3">
            <TabsTrigger value={FORM_TAB.SCHEDULE}>Job setup</TabsTrigger>
            <TabsTrigger value={FORM_TAB.QUERY}>Queries</TabsTrigger>
            <TabsTrigger value={FORM_TAB.EMAIL}>Email</TabsTrigger>
          </TabsList>

          <TabsContent value={FORM_TAB.SCHEDULE} className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
            <JobSetupTab form={form} />
          </TabsContent>

          <TabsContent value={FORM_TAB.QUERY} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
            <QueriesTab form={form} />
          </TabsContent>

          <TabsContent value={FORM_TAB.EMAIL} className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
            <EmailTab form={form} />
          </TabsContent>
        </Tabs>

        {error ? <p className="shrink-0 text-sm text-red-500">{error}</p> : null}

        <DialogFooter className="shrink-0">
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} loading={saving} disabled={saving}>
            {isEditing ? 'Update' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ScheduledJobFormDialog;
