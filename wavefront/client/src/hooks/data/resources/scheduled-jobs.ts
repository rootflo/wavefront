import floConsoleService from '@app/api';
import { ScheduledJob, CreateScheduledJobRequest, UpdateScheduledJobRequest } from '@app/types/scheduled-job';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import { getScheduledJobsKey } from '../query-keys';

// Reads

const SCHEDULED_JOBS_PAGE_SIZE = 20;

const MAX_SCHEDULED_JOBS = 1000;

const getScheduledJobsQueryFn = async (): Promise<ScheduledJob[]> => {
  const jobs: ScheduledJob[] = [];
  let offset = 0;

  while (jobs.length < MAX_SCHEDULED_JOBS) {
    const response = await floConsoleService.scheduledJobService.listScheduledJobs({
      limit: SCHEDULED_JOBS_PAGE_SIZE,
      offset,
    });
    const page = response.data.data?.jobs ?? [];
    jobs.push(...page);
    if (page.length < SCHEDULED_JOBS_PAGE_SIZE) {
      break;
    }
    offset += SCHEDULED_JOBS_PAGE_SIZE;
  }

  return jobs.slice(0, MAX_SCHEDULED_JOBS);
};

export const useGetScheduledJobs = (appId: string | undefined): UseQueryResult<ScheduledJob[], Error> => {
  return useQueryInit(getScheduledJobsKey(appId || ''), getScheduledJobsQueryFn, !!appId);
};

// Writes

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
