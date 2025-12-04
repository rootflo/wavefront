import os

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from common_module.common_cache import CommonCache
from common_module.log.logger import logger


class Scheduler:
    def __init__(self, redis_host: str, redis_port: int, cache_manager: CommonCache):
        self.redis_store = RedisJobStore(
            jobs_key='apscheduler.jobs',
            run_times_key='apscheduler.run_times',
            host=redis_host,
            port=redis_port,
        )

        self.cache_manager: CommonCache = cache_manager
        jobstores = {'default': self.redis_store}

        executors = {'default': ThreadPoolExecutor(os.cpu_count() - 1)}
        job_defaults = {
            'coalesce': False,  # to roll all these missed executions into one.
            'max_instances': 3,  # used to define how many instances of a job are allowed to run concurrently.
        }
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Kolkata',
        )
        self.scheduler.add_listener(self.error_handler, EVENT_JOB_ERROR)

    def start_scheduler(self):
        self.scheduler.remove_all_jobs()
        self.redis_store.remove_all_jobs()
        logger.debug(f'After removing: {self.scheduler.get_jobs()}')
        if not self.scheduler.running:
            self.scheduler.start()

    def register(self, task, cron_params, id):
        try:
            if not id:
                raise ValueError('id must be provided for the task registration.')

            existing_job = self.scheduler.get_job(id)
            lock_key = f'scheduler_lock:{id}'
            if self.cache_manager.add(lock_key, '1', expiry=10, nx=True):
                try:
                    if existing_job:
                        logger.info(f'{id} already exists. Skipping registration')
                    else:
                        logger.info(f'Creating new job {id}')
                        self.scheduler.add_job(
                            task,
                            trigger=CronTrigger(**cron_params),
                            id=id,
                            replace_existing=True,
                        )
                finally:
                    self.cache_manager.remove(lock_key)
            else:
                logger.info('job is getting handled by another  function')

        except Exception as e:
            logger.info(f'Error on task scheduling {e}')

    def is_cron_too_frequent(self, cron_params, min_interval_minutes=60):
        """
        Check if a cron configuration runs more frequently than the specified minimum interval.

        Args:
            cron_params (dict): Dictionary containing cron parameters
            min_interval_minutes (int): Minimum allowed interval in minutes

        Returns:
            tuple: (bool, str) - (True if too frequent, explanation message)
        """
        minute = cron_params.get('minute', '0')
        hour = cron_params.get('hour', '*')
        day = cron_params.get('day', '*')
        month = cron_params.get('month', '*')
        day_of_week = cron_params.get('day_of_week', '*')

        # Check for wildcards in fields that would allow execution more than once per hour
        if any(
            [
                # If minute contains wildcard, comma, hyphen, or step
                ('*' in minute or ',' in minute or '-' in minute or '/' in minute),
                # If hour, day, month, and day_of_week are all wildcards
                (hour == '*' and day == '*' and month == '*' and day_of_week == '*'),
            ]
        ):
            # More complex patterns that could run more frequently than every hour
            if '/' in minute:
                # Check step values like */10 (every 10 minutes)
                try:
                    step = int(minute.split('/')[1])
                    if step < min_interval_minutes:
                        return (
                            True,
                            f'Cron configured to run every {step} minutes, which is more frequent than the minimum allowed interval of {min_interval_minutes} minutes.',
                        )
                except (IndexError, ValueError):
                    pass

            # If there's a wildcard or complex pattern in the minute field, it might run multiple times per hour
            if '*' in minute or ',' in minute or '-' in minute:
                return (
                    True,
                    f"Cron configuration '{minute} {hour} {day} {month} {day_of_week}' may run more frequently than every {min_interval_minutes} minutes.",
                )

        return False, 'Cron configuration meets the minimum interval requirements.'

    def validate_cron_frequency(self, cron_config, min_interval_minutes=60):
        """
        Validate that the cron configuration doesn't run more frequently than specified.

        Args:
            scheduler_config (dict): Dictionary containing scheduler configuration
            min_interval_minutes (int): Minimum allowed interval in minutes

        Returns:
            None

        Raises:
            ValueError: If cron configuration would run more frequently than allowed
        """
        cron_parts = cron_config.split()
        if len(cron_parts) != 5:
            raise ValueError(
                f'Invalid cron configuration. Expected 5 parts but got {len(cron_parts)}'
            )

        cron_params = {
            'minute': cron_parts[0],
            'hour': cron_parts[1],
            'day': cron_parts[2],
            'month': cron_parts[3],
            'day_of_week': cron_parts[4],
        }

        is_too_frequent, message = self.is_cron_too_frequent(
            cron_params, min_interval_minutes
        )
        if is_too_frequent:
            raise ValueError(message)

    def error_handler(self, event):
        logger.info(f'Error handler {event}')

    def log_all_jobs(self):
        logger.info(self.scheduler.get_jobs())
