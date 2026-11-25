import { Button } from '@app/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@app/components/ui/dialog';
import { Form } from '@app/components/ui/form';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@app/components/ui/tabs';
import { FORM_TAB, isFormTab } from '@app/constants/scheduled-job';
import { ScheduledJob } from '@app/types/scheduled-job';
import EmailTab from './EmailTab';
import JobSetupTab from './JobSetupTab';
import QueriesTab from './QueriesTab';
import { useScheduledJobForm } from './useScheduledJobForm';

interface ScheduledJobFormDialogProps {
  isOpen: boolean;
  appId: string;
  job?: ScheduledJob | null;
  onOpenChange: (open: boolean) => void;
}

const ScheduledJobFormDialog: React.FC<ScheduledJobFormDialogProps> = ({ isOpen, appId, job, onOpenChange }) => {
  const state = useScheduledJobForm({ isOpen, appId, job, onOpenChange });
  const { form, isEditing, isEmailJob, activeTab, setActiveTab, saving, handleSave } = state;
  const serverError = form.formState.errors.root?.server?.message;

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[760px] max-h-[calc(100vh-2rem)] max-w-4xl min-w-0 flex-col overflow-hidden lg:max-w-4xl">
        <DialogHeader className="shrink-0">
          <DialogTitle>{isEditing ? 'Edit Scheduled Job' : 'Create Scheduled Job'}</DialogTitle>
          <DialogDescription>
            {isEmailJob
              ? 'Schedule one or more dynamic query reports to be emailed on a cron schedule.'
              : 'Run one or more dynamic queries on a cron schedule. Results are not emailed.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={handleSave} noValidate className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <Tabs
              value={activeTab}
              onValueChange={(value) => {
                if (isFormTab(value)) setActiveTab(value);
              }}
              className="flex min-h-0 flex-1 flex-col overflow-hidden"
            >
              <TabsList className={`grid w-full shrink-0 ${isEmailJob ? 'grid-cols-3' : 'grid-cols-2'}`}>
                <TabsTrigger value={FORM_TAB.SCHEDULE}>Job setup</TabsTrigger>
                <TabsTrigger value={FORM_TAB.QUERY}>Queries</TabsTrigger>
                {isEmailJob ? <TabsTrigger value={FORM_TAB.EMAIL}>Email</TabsTrigger> : null}
              </TabsList>

              <TabsContent value={FORM_TAB.SCHEDULE} className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
                <JobSetupTab state={state} />
              </TabsContent>

              <TabsContent value={FORM_TAB.QUERY} className="mt-4 min-h-0 flex-1 space-y-4 overflow-y-auto">
                <QueriesTab state={state} />
              </TabsContent>

              {isEmailJob ? (
                <TabsContent value={FORM_TAB.EMAIL} className="mt-4 min-h-0 flex-1 space-y-5 overflow-y-auto">
                  <EmailTab state={state} />
                </TabsContent>
              ) : null}
            </Tabs>

            {serverError ? <p className="mt-3 shrink-0 text-sm text-red-500">{serverError}</p> : null}

            <DialogFooter className="mt-4 shrink-0">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" loading={saving} disabled={saving}>
                {isEditing ? 'Update' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default ScheduledJobFormDialog;
