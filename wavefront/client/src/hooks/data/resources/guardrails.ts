import floConsoleService from '@app/api';
import {
  GuardrailAdapterListData,
  GuardrailPolicy,
  PiiEntityListData,
  UpdateGuardrailPolicyRequest,
} from '@app/types/guardrails';
import { useQueryInit } from '@app/lib/react-query';
import { UseQueryResult } from '@tanstack/react-query';
import { useResourceMutation } from './use-resource-mutation';
import {
  getGuardrailPoliciesKey,
  getGuardrailPolicyKey,
  getGuardrailAdaptersKey,
  getGuardrailPiiEntitiesKey,
} from '../query-keys';

// Reads

const getGuardrailPoliciesQueryFn = async (): Promise<GuardrailPolicy[]> => {
  const response = await floConsoleService.guardrailsService.listPolicies();
  if (response.data?.meta?.status === 'success' && response.data.data?.policies) {
    return response.data.data.policies;
  }
  return [];
};

const getGuardrailPolicyQueryFn = async (namespace: string): Promise<GuardrailPolicy | null> => {
  const response = await floConsoleService.guardrailsService.getPolicy(namespace);
  if (response.data?.meta?.status === 'success' && response.data.data?.policy) {
    return response.data.data.policy;
  }
  return null;
};

const getGuardrailAdaptersQueryFn = async (): Promise<GuardrailAdapterListData> => {
  const response = await floConsoleService.guardrailsService.listSupportedAdapters();
  if (response.data?.meta?.status === 'success' && response.data.data) {
    return response.data.data;
  }
  return { adapters: [], unavailable: [] };
};

const getGuardrailPiiEntitiesQueryFn = async (): Promise<PiiEntityListData> => {
  const response = await floConsoleService.guardrailsService.listPiiEntities();
  if (response.data?.meta?.status === 'success' && response.data.data) {
    return response.data.data;
  }
  return { groups: [], available: false };
};

export const useGetGuardrailPolicies = (appId: string | undefined): UseQueryResult<GuardrailPolicy[], Error> => {
  return useQueryInit(getGuardrailPoliciesKey(appId || ''), getGuardrailPoliciesQueryFn, !!appId);
};

export const useGetGuardrailPolicy = (
  appId: string | undefined,
  namespace: string | undefined
): UseQueryResult<GuardrailPolicy | null, Error> => {
  return useQueryInit(
    getGuardrailPolicyKey(appId || '', namespace || ''),
    () => getGuardrailPolicyQueryFn(namespace!),
    !!appId && !!namespace
  );
};

export const useGetGuardrailAdapters = (appId: string | undefined): UseQueryResult<GuardrailAdapterListData, Error> => {
  return useQueryInit(getGuardrailAdaptersKey(appId || ''), getGuardrailAdaptersQueryFn, !!appId);
};

/**
 * The entity types this deployment can detect.
 *
 * Fixed for the life of the server process — the recogniser registry is built
 * once at startup — and the first call pays for loading a spaCy model, so this
 * is deliberately never refetched.
 */
export const useGetGuardrailPiiEntities = (appId: string | undefined): UseQueryResult<PiiEntityListData, Error> => {
  return useQueryInit(getGuardrailPiiEntitiesKey(appId || ''), getGuardrailPiiEntitiesQueryFn, !!appId);
};

// Writes

export const useSaveGuardrailPolicy = (appId: string | undefined) =>
  useResourceMutation({
    mutationFn: ({ namespace, data }: { namespace: string; data: UpdateGuardrailPolicyRequest }) =>
      floConsoleService.guardrailsService.updatePolicy(namespace, data),
    successMessage: 'Guardrail policy saved',
    errorMessage: 'Failed to save guardrail policy',
    invalidate: ({ namespace }) =>
      appId ? [getGuardrailPolicyKey(appId, namespace), getGuardrailPoliciesKey(appId)] : [],
  });
