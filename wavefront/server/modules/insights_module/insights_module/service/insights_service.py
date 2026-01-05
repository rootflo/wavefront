from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from typing import Dict, List, Any

from common_module.log.logger import logger
from insights_module.models.insights_signal import ActionableAlerts
from insights_module.models.insights_signal import Alert
from insights_module.models.insights_signal import AlertType
from insights_module.models.insights_signal import DataPoints
from insights_module.models.insights_signal import DetailedInsights
from insights_module.models.insights_signal import Metric
from insights_module.models.insights_signal_query import Periodicity
from insights_module.models.insights_signal_query import Projection
from insights_module.models.insights_signal_query import Projections
from insights_module.models.insights_signal_query import SignalQuery
from insights_module.models.insights_signal_query import Threshold
from insights_module.repository.pvo_repository import PVORepository


@dataclass
class QueryWindow:
    name: str
    start: datetime
    end: datetime
    alerts: List[Threshold]


class InsightsService:
    def __init__(
        self,
        repository: PVORepository,
        today_as_max_from_db: str = 'false',
    ):
        self.repository = repository
        self.today_as_max_from_db = today_as_max_from_db == 'true'
        self.current_date = datetime.today() - timedelta(days=1)

        if self.today_as_max_from_db:
            max_date = self.repository.get_max_record_date()
            logger.info(f'Configuring current date as: {max_date}')
            self.current_date = max_date if max_date is not None else self.current_date

    def __get_windows(self, name: str, number_of_days: int, alerts: List[Threshold]):
        today = self.current_date
        logger.info(f'Max date used for running worker: {today}')
        return (
            QueryWindow(
                name=name,
                start=(today - timedelta(days=number_of_days * 2)).strftime('%Y-%m-%d'),
                end=(today - timedelta(days=number_of_days)).strftime('%Y-%m-%d'),
                alerts=alerts,
            ),
            QueryWindow(
                name=name,
                start=(today - timedelta(days=number_of_days)).strftime('%Y-%m-%d'),
                end=today.strftime('%Y-%m-%d'),
                alerts=alerts,
            ),
        )

    def __fetch_periods(self, peroids: list[Periodicity]):
        diff_window = []
        for period in peroids:
            if period.period.startswith('L') and period.period.endswith('D'):
                period_day_count = int(
                    period.period.removeprefix('L').removesuffix('D')
                )
                diff_window.append(
                    self.__get_windows(period.period, period_day_count, period.alerts)
                )
            else:
                logger.warning(f'Unknown periodicity found: {period.period}')
        return diff_window

    def __fetch_parent_projections(self, projections: Projections):
        projections: list[Projection] = projections.parent
        projection_queries = [
            f'{projection.sql} as {projection.metric}' for projection in projections
        ]

        return ','.join(projection_queries), projections

    def __fetch_child_projections(self, projections: Projections):
        projections: list[Projection] = projections.children
        projection_queries = [
            f'{projection.sql} as {projection.metric}' for projection in projections
        ]
        return ','.join(projection_queries), projections

    def __execute_periodic_insights(
        self, query, projection_query, old_window: QueryWindow, new_window: QueryWindow
    ):
        old_window_value: dict = self.repository.fetch_insights(
            query,
            projection_query,
            start_date=old_window.start,
            end_date=old_window.end,
        )

        new_window_value: dict = self.repository.fetch_insights(
            query,
            projection_query,
            start_date=new_window.start,
            end_date=new_window.end,
        )
        return old_window_value, new_window_value

    def __periodic_alerts(
        self,
        period_name: str,
        old_window_value: float,
        new_window_value: float,
        possible_alerts: List[Threshold],
    ) -> List[Alert]:
        alerts_to_notify: List[Alert] = []
        for alert in possible_alerts:
            metric = alert.metric
            threshold = alert.threshold

            old_values = old_window_value.get(metric, [])
            new_values = new_window_value.get(metric, [])

            if (
                old_values is None
                or new_values is None
                or len(old_values) == 0
                or len(new_values) == 0
            ):
                logger.debug(
                    f'No value found for metric: {metric}, skipping alert creation'
                )
                continue

            if new_values[0] is None or old_values[0] is None:
                logger.debug(
                    f'Possibly missing data, old {old_values[0]} and new {new_values[0]}'
                )
                continue

            diff_value = new_values[0] - old_values[0]
            diff_percentage = diff_value / old_values[0] if old_values[0] != 0 else None
            if self.__check_threshold(threshold, diff_percentage):
                logger.info(
                    f'metric: {metric}, threshould: {threshold}, diff_percentage: {diff_percentage}, type: {period_name}'
                )
                alerts_to_notify.append(
                    Alert(
                        metric=metric,
                        threshold=threshold,
                        diff_value=diff_percentage,
                        previous_value=old_values[0],
                        current_value=new_values[0],
                        type=AlertType.resolve(period_name),
                    )
                )
        return alerts_to_notify

    def __check_threshold(self, threshold: float, value: float):
        if value is None:
            return False
        return (threshold > 0 and value > threshold) or (
            threshold < 0 and value < threshold
        )

    def __goal_line_alerts(self, goal_lines: List[Threshold], new_window_value):
        alerts = []
        for line in goal_lines:
            new_values = new_window_value.get(line.metric, [])
            if len(new_values) == 0 or new_values[0] is None:
                logger.debug(
                    f'No value found for metric: {line.metric}, skipping alert creation'
                )
                continue
            logger.info(
                f'metric: {line.metric}, threshould: {line.threshold}, value: {new_values[0]}, type: {AlertType.goal_line}'
            )
            if (line.threshold > 0 and new_values[0] >= line.threshold) or (
                line.threshold < 0 and new_values[0] <= line.threshold
            ):
                alerts.append(
                    Alert(
                        metric=line.metric,
                        threshold=line.threshold,
                        current_value=new_values[0],
                        previous_value=None,
                        diff_value=None,
                        type=AlertType.goal_line,
                    )
                )
        return alerts

    # TODO remove periodicity_filter and make it part of yaml
    def maybe_extract_alerts(
        self, insight_query: SignalQuery, periodicity_filter: str = None
    ):
        periods = self.__fetch_periods(insight_query.periodicity)
        projection_query, _ = self.__fetch_parent_projections(insight_query.projections)

        alerts: List[Alert] = []
        new_value_7d = None
        for period in periods:
            old_window, new_window = period
            if periodicity_filter is not None:
                if periodicity_filter != new_window.name:
                    continue
            old_value, new_value = self.__execute_periodic_insights(
                insight_query.query.sql, projection_query, old_window, new_window
            )
            # TODO goal line will only be checked for L7D
            if new_window.name == 'L7D':
                new_value_7d = new_value
            periodic_alerts = self.__periodic_alerts(
                period_name=old_window.name,
                old_window_value=old_value,
                new_window_value=new_value,
                possible_alerts=old_window.alerts,
            )
            alerts.extend(periodic_alerts)

        goal_line_alerts = []
        if new_value_7d:
            goal_line_alerts = self.__goal_line_alerts(
                insight_query.goal_lines, new_value_7d
            )

        alerts.extend(goal_line_alerts)

        return ActionableAlerts(
            id=insight_query.id,
            name=insight_query.name,
            title=insight_query.title,
            type=insight_query.type,
            description=insight_query.description,
            alerts=alerts,
        )

    def __safe_fetch_metric(self, results: dict, metric: str):
        value = results.get(metric, [])
        return value[0] if len(value) > 0 else None

    def extract_raw_inner_query(self, insight_query: SignalQuery):
        detailed_period = 'L7D'
        if len(insight_query.periodicity) > 0:
            detailed_period = insight_query.periodicity[0].period
            period_day_count = int(detailed_period.removeprefix('L').removesuffix('D'))

        # picked the first window
        _, new_window = self.__get_windows(detailed_period, period_day_count, [])
        return self.repository.execute_query(
            insight_query.query.sql,
            start_date=new_window.start,
            end_date=new_window.end,
        )

    def extract_detailed_insights(self, insight_query: SignalQuery):
        projection_query, projections = self.__fetch_child_projections(
            insight_query.projections
        )

        detailed_period = 'L7D'
        if len(insight_query.periodicity) > 0:
            detailed_period = insight_query.periodicity[0].period
            period_day_count = int(detailed_period.removeprefix('L').removesuffix('D'))

        # picked the first window
        old_window, new_window = self.__get_windows(
            detailed_period, period_day_count, []
        )

        results = self.repository.fetch_insights(
            insight_query.query.sql,
            projection_query,
            start_date=new_window.start,
            end_date=new_window.end,
        )

        metrices = [
            Metric(
                metric=projection.metric,
                name=projection.name,
                value=self.__safe_fetch_metric(
                    results=results, metric=projection.metric
                ),
            )
            for projection in projections
        ]

        if insight_query.plots is None or len(insight_query.plots) == 0:
            logger.error('The insights query plots seems to be empty')
            return DetailedInsights(
                metrices=metrices, data_points=None, goal_lines=insight_query.goal_lines
            )

        projections = [p for p in insight_query.plots[0].metrices]
        projection_queries = [
            f'{projection.sql} as {projection.metric}' for projection in projections
        ]
        pr_query = ','.join(projection_queries)

        raw_data_new: Dict[str, List] = self.repository.fetch_raw_values(
            insight_query.query.sql,
            projection=pr_query,
            start_date=new_window.start,
            end_date=new_window.end,
        )

        raw_data_old: Dict[str, List] = self.repository.fetch_raw_values(
            insight_query.query.sql,
            projection=pr_query,
            start_date=old_window.start,
            end_date=old_window.end,
        )

        return DetailedInsights(
            metrices=metrices,
            data_points=DataPoints(
                window_type='L7D', old_window=raw_data_old, new_window=raw_data_new
            ),
            goal_lines=insight_query.goal_lines,
        )

    def fetch_pvo_records(
        self,
        odata_query: str | None = None,
        params: Dict | None = None,
        limit: str | None = None,
        offset: str | None = None,
        table_name: str = None,
    ) -> List:
        return self.repository.fetch_pvo_record(
            odata_query,
            params=params,
            limit=limit,
            offset=offset,
            table_name=table_name,
        )

    def update_pvo_records_by_id(
        self,
        id: str,
        table_name: str,
        rls_filter: str,
        rls_params: Dict[str, Any],
        update_data: Dict[str, Any],
    ) -> List:
        return self.repository.update_pvo_record(
            id=id,
            table_name=table_name,
            update_data=update_data,
            odata_condition=rls_filter,
            rls_params=rls_params,
        )
