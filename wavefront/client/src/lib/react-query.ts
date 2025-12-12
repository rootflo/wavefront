import { QueryKey, QueryFunction, useQuery } from '@tanstack/react-query';

const useQueryInit = <T>(
  queryKey: QueryKey,
  queryFn: QueryFunction<T>,
  enabled: boolean = true,
  refetchInterval?: number,
  refetchOnMount?: boolean
) => {
  return useQuery<T>({
    queryKey,
    queryFn,
    enabled: enabled,
    retry: false,
    refetchOnWindowFocus: false,
    ...(refetchOnMount !== undefined && { refetchOnMount }),
    ...(refetchInterval !== undefined && { refetchInterval }),
  });
};

export { useQueryInit };
