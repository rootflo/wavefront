import floConsoleService from '@app/api';
import { CreateScheduledJobRequest, UpdateScheduledJobRequest } from '@app/types/scheduled-job';
import { getScheduledJobsKey } from '../query-keys';
import { useResourceMutation } from './use-resource-mutation';

/** No error toast: the job form shows a failure inline. */
export const useCreateScheduledJob = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (request: CreateScheduledJobRequest) =>
      floConsoleService.scheduledJobService.createScheduledJob(request),
    successMessage: 'Scheduled job created successfully',
    errorMessage: false,
    invalidate: () => [appId && getScheduledJobsKey(appId)],
  });

/** No error toast: the job form shows a failure inline. */
export const useUpdateScheduledJob = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ jobId, request }: { jobId: string; request: UpdateScheduledJobRequest }) =>
      floConsoleService.scheduledJobService.updateScheduledJob(jobId, request),
    successMessage: 'Scheduled job updated successfully',
    errorMessage: false,
    invalidate: () => [appId && getScheduledJobsKey(appId)],
  });

/** Pauses an active job, or resumes a paused or failed one. */
export const useSetScheduledJobPaused = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ jobId, paused }: { jobId: string; paused: boolean; wasFailed?: boolean }) =>
      paused
        ? floConsoleService.scheduledJobService.pauseScheduledJob(jobId)
        : floConsoleService.scheduledJobService.resumeScheduledJob(jobId),
    successMessage: (_, { paused, wasFailed }) => {
      if (paused) return 'Scheduled job paused';
      return wasFailed ? 'Scheduled job resumed; it will run on the next scheduler poll' : 'Scheduled job resumed';
    },
    errorMessage: 'Failed to update job status',
    invalidate: () => [appId && getScheduledJobsKey(appId)],
  });

export const useDeleteScheduledJob = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: (jobId: string) => floConsoleService.scheduledJobService.deleteScheduledJob(jobId),
    successMessage: 'Scheduled job deleted',
    errorMessage: 'Failed to delete scheduled job',
    invalidate: () => [appId && getScheduledJobsKey(appId)],
  });
