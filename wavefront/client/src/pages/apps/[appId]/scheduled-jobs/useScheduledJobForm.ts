import { FORM_TAB, JOB_TYPE_EMAIL_DYNAMIC_QUERY } from '@app/constants/scheduled-job';
import {
  useCreateScheduledJob,
  useGetAllDatasources,
  useGetAllDynamicQueries,
  useGetAppUsers,
  useGetEmailConnections,
  useUpdateScheduledJob,
} from '@app/hooks';
import { FormTab, ScheduledJob } from '@app/types/scheduled-job';
import { zodResolver } from '@hookform/resolvers/zod';
import { useEffect, useMemo, useState } from 'react';
import { FieldErrors, useFieldArray, useForm, useWatch } from 'react-hook-form';
import { getDynamicQueryIdFromFileName } from '../datasources/dynamic-query-utils';
import { ScheduledJobFormValues, scheduledJobFormSchema, toFormValues, toPayload } from './scheduled-job-form';

interface UseScheduledJobFormArgs {
  isOpen: boolean;
  appId: string;
  /** The job being edited; omit when creating one. */
  job?: ScheduledJob | null;
  onOpenChange: (open: boolean) => void;
}

/** The tab each top-level field lives on, in the order the tabs are checked for errors. */
const TAB_FOR_FIELD: Record<keyof ScheduledJobFormValues, FormTab> = {
  jobType: FORM_TAB.SCHEDULE,
  cronExpr: FORM_TAB.SCHEDULE,
  timezone: FORM_TAB.SCHEDULE,
  maxRetries: FORM_TAB.SCHEDULE,
  datasourceId: FORM_TAB.SCHEDULE,
  defaults: FORM_TAB.SCHEDULE,
  queries: FORM_TAB.QUERY,
  recipientUserIds: FORM_TAB.EMAIL,
  emailConnectionId: FORM_TAB.EMAIL,
  subject: FORM_TAB.EMAIL,
  emailContent: FORM_TAB.EMAIL,
};

/**
 * The scheduled job form (react-hook-form + zod), the data its pickers list, and saving.
 * An invalid save switches to the first tab with a problem; errors show next to their fields.
 */
export const useScheduledJobForm = ({ isOpen, appId, job, onOpenChange }: UseScheduledJobFormArgs) => {
  const isEditing = Boolean(job?.id);
  const form = useForm<ScheduledJobFormValues>({
    resolver: zodResolver(scheduledJobFormSchema),
    defaultValues: toFormValues(job),
  });
  const queryFields = useFieldArray({ control: form.control, name: 'queries' });
  const [activeTab, setActiveTab] = useState<FormTab>(FORM_TAB.SCHEDULE);

  useEffect(() => {
    if (!isOpen) return;
    form.reset(toFormValues(job));
    setActiveTab(FORM_TAB.SCHEDULE);
  }, [isOpen, job, form]);

  const jobType = useWatch({ control: form.control, name: 'jobType' });
  const datasourceId = useWatch({ control: form.control, name: 'datasourceId' });
  const isEmailJob = jobType === JOB_TYPE_EMAIL_DYNAMIC_QUERY;
  // Scheduled query jobs have no Email tab.
  const visibleTab = !isEmailJob && activeTab === FORM_TAB.EMAIL ? FORM_TAB.SCHEDULE : activeTab;

  const { data: datasources = [] } = useGetAllDatasources(appId);
  const { data: appUsers = [], isLoading: appUsersLoading } = useGetAppUsers(appId);
  const { data: emailConnections = [] } = useGetEmailConnections(appId);
  const { data: dynamicQueries = [], isLoading: dynamicQueriesLoading } = useGetAllDynamicQueries(
    appId,
    datasourceId || undefined
  );
  const availableQueryIds = useMemo(
    () => dynamicQueries.map((query) => getDynamicQueryIdFromFileName(query.file)).filter((id) => id.length > 0),
    [dynamicQueries]
  );
  const sendableConnections = useMemo(
    () => emailConnections.filter((connection) => connection.status === 'active'),
    [emailConnections]
  );

  const createScheduledJob = useCreateScheduledJob(appId);
  const updateScheduledJob = useUpdateScheduledJob(appId);
  const saving = createScheduledJob.isPending || updateScheduledJob.isPending;

  // No dismissing mid-save: the save's completion closes or errors this dialog, and must not land
  // on another job opened in the meantime.
  const handleOpenChange = (open: boolean) => {
    if (!open && saving) return;
    onOpenChange(open);
  };

  const onValid = (values: ScheduledJobFormValues) => {
    const callbacks = {
      onSuccess: () => onOpenChange(false),
      onError: () =>
        form.setError('root.server', {
          message: 'Unable to save scheduled job. Please verify the details and try again.',
        }),
    };
    const fields = {
      cron_expr: values.cronExpr,
      timezone: values.timezone,
      max_retries: Number(values.maxRetries),
      payload: toPayload(values),
    };
    if (isEditing && job) {
      updateScheduledJob.mutate({ jobId: job.id, request: fields }, callbacks);
    } else {
      createScheduledJob.mutate({ job_type: values.jobType, ...fields }, callbacks);
    }
  };

  const onInvalid = (errors: FieldErrors<ScheduledJobFormValues>) => {
    const firstField = (Object.keys(TAB_FOR_FIELD) as (keyof ScheduledJobFormValues)[]).find((key) => errors[key]);
    if (firstField) setActiveTab(TAB_FOR_FIELD[firstField]);
  };

  return {
    form,
    queryFields,
    job,
    isEditing,
    isEmailJob,
    activeTab: visibleTab,
    setActiveTab,
    saving,
    handleOpenChange,
    handleSave: form.handleSubmit(onValid, onInvalid),
    datasources,
    appUsers,
    appUsersLoading,
    sendableConnections,
    availableQueryIds,
    dynamicQueriesLoading,
  };
};

export type ScheduledJobFormState = ReturnType<typeof useScheduledJobForm>;
