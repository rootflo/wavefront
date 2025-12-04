import collections


def fetch_data_filters(data_filters: list) -> str:
    group_filter = collections.defaultdict(list)
    for data_filter in data_filters:
        group_filter[data_filter.key].append(data_filter.value)

    additional_filters = []
    for key, values in group_filter.items():
        if len(values) == 1:
            additional_filters.append(f"({key} eq '{values[0]}')")
        else:
            or_condition = []
            for value in values:
                or_condition.append(f"({key} eq '{value}')")
            additional_filters.append(f"({'$or'.join(or_condition)})")

    return additional_filters
