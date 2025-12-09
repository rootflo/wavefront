import floConsoleService from "@app/api";
import {
  cleanParameters,
  getProviderBadge,
  getProviderConfig,
  mergeParameters,
} from "@app/config/authenticators";
import { useGetAuthenticator } from "@app/hooks/data/fetch-hooks";
import { useNotifyStore } from "@app/store";
import { useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";

const AuthenticatorDetailPage: React.FC = () => {
  const { app, authId } = useParams<{ app: string; authId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [togglingEnabled, setTogglingEnabled] = useState(false);

  // Form state
  const [authDesc, setAuthDesc] = useState("");
  const [parameters, setParameters] = useState<Record<string, any>>({});

  // Fetch authenticator
  const { data: authenticator, isLoading: authenticatorLoading } =
    useGetAuthenticator(app, authId);

  // Initialize form with authenticator data
  useEffect(() => {
    if (authenticator) {
      setAuthDesc(authenticator.auth_desc || "");
      setParameters(
        mergeParameters(authenticator.auth_type, authenticator.config)
      );
    }
  }, [authenticator]);

  const setParameter = (key: string, value: any) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const setNestedParameter = (
    parentKey: string,
    childKey: string,
    value: any
  ) => {
    setParameters((prev) => ({
      ...prev,
      [parentKey]: {
        ...prev[parentKey],
        [childKey]: value,
      },
    }));
  };

  const handleCancel = () => {
    if (authenticator) {
      setAuthDesc(authenticator.auth_desc || "");
      setParameters(
        mergeParameters(authenticator.auth_type, authenticator.config)
      );
    }
    setIsEditing(false);
  };

  const handleSave = async () => {
    if (!authId) return;

    setSaveLoading(true);
    try {
      await floConsoleService.authenticatorService.updateAuthenticator(authId, {
        auth_desc: authDesc.trim() || null,
        config: cleanParameters(parameters),
      });
      notifySuccess("Authenticator updated successfully");
      setIsEditing(false);
      queryClient.invalidateQueries({
        queryKey: ["authenticator", app, authId],
      });
      queryClient.invalidateQueries({ queryKey: ["authenticators", app] });
    } catch (error: any) {
      notifyError(
        error?.response?.data?.meta?.error || "Failed to update authenticator"
      );
    } finally {
      setSaveLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!authId) return;

    try {
      await floConsoleService.authenticatorService.deleteAuthenticator(authId);
      notifySuccess("Authenticator deleted successfully");
      navigate(`/apps/${app}/authenticators`);
    } catch (error: any) {
      notifyError(
        error?.response?.data?.meta?.error || "Failed to delete authenticator"
      );
    }
  };

  const handleToggleEnabled = async () => {
    if (!authId || !authenticator) return;

    setTogglingEnabled(true);
    try {
      if (authenticator.is_enabled) {
        await floConsoleService.authenticatorService.disableAuthenticator(
          authId
        );
        notifySuccess("Authenticator disabled successfully");
      } else {
        await floConsoleService.authenticatorService.enableAuthenticator(
          authId
        );
        notifySuccess("Authenticator enabled successfully");
      }
      queryClient.invalidateQueries({
        queryKey: ["authenticator", app, authId],
      });
      queryClient.invalidateQueries({ queryKey: ["authenticators", app] });
    } catch (error: any) {
      notifyError(
        error?.response?.data?.meta?.error || "Failed to toggle authenticator"
      );
    } finally {
      setTogglingEnabled(false);
    }
  };

  const renderParameterField = (key: string, disabled: boolean) => {
    if (!authenticator) return null;

    const config = getProviderConfig(authenticator.auth_type);
    if (!config) return null;

    const paramConfig = config.parameters[key];
    if (!paramConfig) return null;

    // Handle nested object parameters (like password_policy)
    if (paramConfig.type === "object" && paramConfig.fields) {
      return (
        <div className="space-y-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
          <label className="block text-sm font-medium text-gray-700">
            {key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </label>
          {paramConfig.description && (
            <p className="text-xs text-gray-500">{paramConfig.description}</p>
          )}
          <div className="space-y-3">
            {Object.entries(paramConfig.fields).map(
              ([nestedKey, nestedConfig]) => (
                <div key={nestedKey}>
                  <label className="mb-1 block text-xs font-medium text-gray-700">
                    {nestedKey
                      .replace(/_/g, " ")
                      .replace(/\b\w/g, (l) => l.toUpperCase())}
                  </label>
                  {nestedConfig.description && (
                    <p className="mb-1 text-xs text-gray-500">
                      {nestedConfig.description}
                    </p>
                  )}
                  {renderNestedField(key, nestedKey, nestedConfig, disabled)}
                </div>
              )
            )}
          </div>
        </div>
      );
    }

    // Handle array parameters (like scopes)
    if (paramConfig.type === "array") {
      const arrayValue = Array.isArray(parameters[key])
        ? parameters[key].join(", ")
        : "";
      return (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </label>
          {paramConfig.description && (
            <p className="mb-1 text-xs text-gray-500">
              {paramConfig.description}
            </p>
          )}
          <input
            type="text"
            value={arrayValue}
            onChange={(e) => {
              const values = e.target.value
                .split(",")
                .map((v) => v.trim())
                .filter(Boolean);
              setParameter(key, values);
            }}
            disabled={disabled}
            placeholder={paramConfig.placeholder}
            className={clsx(
              "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
              disabled && "cursor-not-allowed bg-gray-50 text-gray-500"
            )}
          />
          <p className="mt-1 text-xs text-gray-500">
            Separate multiple values with commas
          </p>
        </div>
      );
    }

    // Handle boolean parameters
    if (paramConfig.type === "boolean") {
      return (
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={parameters[key] || false}
            onChange={(e) => setParameter(key, e.target.checked)}
            disabled={disabled}
            className={clsx(
              "h-4 w-4 rounded border-gray-300 text-black focus:ring-black",
              disabled && "cursor-not-allowed opacity-50"
            )}
          />
          <div>
            <label className="text-sm font-medium text-gray-700">
              {key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
            </label>
            {paramConfig.description && (
              <p className="text-xs text-gray-500">{paramConfig.description}</p>
            )}
          </div>
        </div>
      );
    }

    // Handle number parameters
    if (paramConfig.type === "number") {
      return (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </label>
          {paramConfig.description && (
            <p className="mb-1 text-xs text-gray-500">
              {paramConfig.description}
            </p>
          )}
          <input
            type="number"
            value={parameters[key] ?? ""}
            onChange={(e) =>
              setParameter(key, e.target.value ? Number(e.target.value) : "")
            }
            disabled={disabled}
            min={paramConfig.min}
            max={paramConfig.max}
            step={paramConfig.step}
            placeholder={paramConfig.placeholder}
            className={clsx(
              "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
              disabled && "cursor-not-allowed bg-gray-50 text-gray-500"
            )}
          />
        </div>
      );
    }

    // Handle select parameters
    if (paramConfig.type === "select" && paramConfig.options) {
      return (
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            {key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </label>
          {paramConfig.description && (
            <p className="mb-1 text-xs text-gray-500">
              {paramConfig.description}
            </p>
          )}
          <select
            value={parameters[key] || ""}
            onChange={(e) => setParameter(key, e.target.value)}
            disabled={disabled}
            className={clsx(
              "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
              disabled && "cursor-not-allowed bg-gray-50 text-gray-500"
            )}
          >
            {paramConfig.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      );
    }

    // Default: string input
    return (
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          {key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
        </label>
        {paramConfig.description && (
          <p className="mb-1 text-xs text-gray-500">
            {paramConfig.description}
          </p>
        )}
        <input
          type="text"
          value={parameters[key] || ""}
          onChange={(e) => setParameter(key, e.target.value)}
          disabled={disabled}
          placeholder={paramConfig.placeholder}
          className={clsx(
            "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
            disabled && "cursor-not-allowed bg-gray-50 text-gray-500"
          )}
        />
      </div>
    );
  };

  const renderNestedField = (
    parentKey: string,
    childKey: string,
    config: any,
    disabled: boolean
  ) => {
    const value = parameters[parentKey]?.[childKey];

    if (config.type === "boolean") {
      return (
        <input
          type="checkbox"
          checked={value || false}
          onChange={(e) =>
            setNestedParameter(parentKey, childKey, e.target.checked)
          }
          disabled={disabled}
          className={clsx(
            "h-4 w-4 rounded border-gray-300 text-black focus:ring-black",
            disabled && "cursor-not-allowed opacity-50"
          )}
        />
      );
    }

    if (config.type === "number") {
      return (
        <input
          type="number"
          value={value ?? ""}
          onChange={(e) =>
            setNestedParameter(
              parentKey,
              childKey,
              e.target.value ? Number(e.target.value) : ""
            )
          }
          disabled={disabled}
          min={config.min}
          max={config.max}
          step={config.step}
          className={clsx(
            "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
            disabled && "cursor-not-allowed bg-gray-50 text-gray-500"
          )}
        />
      );
    }

    return (
      <input
        type="text"
        value={value || ""}
        onChange={(e) =>
          setNestedParameter(parentKey, childKey, e.target.value)
        }
        disabled={disabled}
        placeholder={config.placeholder}
        className={clsx(
          "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
          disabled && "cursor-not-allowed bg-gray-50 text-gray-500"
        )}
      />
    );
  };

  if (authenticatorLoading) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="mx-auto max-w-3xl">
          <div className="text-center">Loading authenticator...</div>
        </div>
      </div>
    );
  }

  if (!authenticator) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="mx-auto max-w-3xl">
          <div className="text-center text-red-600">
            Authenticator not found
          </div>
        </div>
      </div>
    );
  }

  const config = getProviderConfig(authenticator.auth_type);
  const badge = getProviderBadge(authenticator.auth_type);

  return (
    <div className="min-h-screen bg-white p-6">
      <div className="mx-auto max-w-3xl">
        {/* Go Back Button */}
        <div
          className="mb-6 flex cursor-pointer items-center gap-2"
          onClick={() => navigate(`/apps/${app}/authenticators`)}
        >
          <p className="text-normal text-base text-[#101010]">Go back</p>
        </div>

        {/* Header */}
        <div className="mb-6 flex items-start justify-between">
          <div className="flex-1">
            <div className="mb-2 flex items-center gap-3">
              <h1 className="text-2xl font-bold text-gray-900">
                {authenticator.auth_name}
              </h1>
              <span
                className={clsx(
                  "rounded-full px-3 py-1 text-xs font-medium",
                  badge.bg,
                  badge.text
                )}
              >
                {config?.name || authenticator.auth_type}
              </span>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-500">
                  Status:
                </span>
                <span
                  className={clsx(
                    "text-sm font-medium",
                    authenticator.is_enabled
                      ? "text-green-600"
                      : "text-gray-400"
                  )}
                >
                  {authenticator.is_enabled ? "Enabled" : "Disabled"}
                </span>
              </div>
              <button
                onClick={handleToggleEnabled}
                disabled={togglingEnabled}
                className={clsx(
                  "relative inline-flex h-6 w-11 items-center rounded-full transition-colors",
                  authenticator.is_enabled ? "bg-black" : "bg-gray-200",
                  togglingEnabled && "cursor-not-allowed opacity-50"
                )}
              >
                <span
                  className={clsx(
                    "inline-block h-4 w-4 transform rounded-full bg-white transition-transform",
                    authenticator.is_enabled ? "translate-x-6" : "translate-x-1"
                  )}
                />
              </button>
            </div>
          </div>
          <div className="flex gap-2">
            {!isEditing ? (
              <>
                <button
                  onClick={() => setIsEditing(true)}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Edit
                </button>
                <button
                  onClick={() => setShowDeleteModal(true)}
                  className="rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
                >
                  Delete
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleCancel}
                  disabled={saveLoading}
                  className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saveLoading}
                  className={clsx(
                    "rounded-md bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800",
                    saveLoading && "cursor-not-allowed opacity-50"
                  )}
                >
                  {saveLoading ? "Saving..." : "Save Changes"}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Form */}
        <div className="space-y-6">
          {/* Description */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Description
            </label>
            <textarea
              value={authDesc}
              onChange={(e) => setAuthDesc(e.target.value)}
              disabled={!isEditing}
              rows={3}
              maxLength={500}
              placeholder="Optional description for this authenticator"
              className={clsx(
                "w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-black focus:outline-none focus:ring-1 focus:ring-black",
                !isEditing && "cursor-not-allowed bg-gray-50 text-gray-500"
              )}
            />
            {isEditing && (
              <p className="mt-1 text-xs text-gray-500">
                {authDesc.length}/500 characters
              </p>
            )}
          </div>

          {/* Configuration Parameters */}
          {config && (
            <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-6">
              <h3 className="text-lg font-semibold text-gray-900">
                Configuration
              </h3>
              <div className="space-y-4">
                {Object.keys(config.parameters).map((key) => (
                  <div key={key}>{renderParameterField(key, !isEditing)}</div>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-6">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">
              Metadata
            </h3>
            <dl className="space-y-3">
              <div>
                <dt className="text-xs font-medium text-gray-500">
                  Authenticator ID
                </dt>
                <dd className="mt-1 font-mono text-sm text-gray-900">
                  {authenticator.auth_id}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500">
                  Created At
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {new Date(authenticator.created_at).toLocaleString()}
                </dd>
              </div>
              <div>
                <dt className="text-xs font-medium text-gray-500">
                  Updated At
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {new Date(authenticator.updated_at).toLocaleString()}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="mx-4 w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">
              Delete Authenticator
            </h3>
            <p className="mb-6 text-sm text-gray-600">
              Are you sure you want to delete "{authenticator.auth_name}"? This
              action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AuthenticatorDetailPage;
