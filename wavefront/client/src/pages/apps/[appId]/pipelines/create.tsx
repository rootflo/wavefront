import floConsoleService from '@app/api';
import { useNotifyStore } from '@app/store';
import { CreatePipelineRequest } from '@app/types/pipeline';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';

const CreatePipeline: React.FC = () => {
  const { app } = useParams<{ app: string }>();
  const navigate = useNavigate();
  const { notifySuccess, notifyError } = useNotifyStore();
  const [loading, setLoading] = useState(false);

  const [formData, setFormData] = useState<CreatePipelineRequest>({
    project_name: '',
    description: '',
    schedule_interval: '0 6 * * *',
    start_at: new Date().toISOString().slice(0, 16),
    type: 'dbt',
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.project_name.trim()) {
      newErrors.project_name = 'Project name is required';
    }

    if (!formData.start_at) {
      newErrors.start_at = 'Start date is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);

    try {
      const response = await floConsoleService.dataPipelineService.createPipeline({
        ...formData,
        start_at: new Date(formData.start_at).toISOString(),
      });

      notifySuccess('Pipeline created successfully');
      navigate(`/apps/${app}/data-pipelines/${response.data?.data?.pipeline?.pipeline_id}`);
    } catch (error) {
      console.error('Error creating pipeline:', error);
      notifyError('Failed to create pipeline');
      setLoading(false);
    }
  };

  const handleCancel = () => {
    navigate(`/apps/${app}/data-pipelines`);
  };

  return (
    <div className="min-h-screen bg-white p-6">
      <div className="mx-auto max-w-3xl">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Create Pipeline</h1>
          <p className="mt-2 text-gray-600">Configure a new DBT pipeline</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="project_name" className="block text-sm font-medium text-gray-700">
              Project Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              id="project_name"
              value={formData.project_name}
              onChange={(e) => setFormData({ ...formData, project_name: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-black focus:outline-none focus:ring-black"
              placeholder="my_analytics_pipeline"
            />
            {errors.project_name && <p className="mt-1 text-sm text-red-600">{errors.project_name}</p>}
          </div>

          <div>
            <label htmlFor="description" className="block text-sm font-medium text-gray-700">
              Description
            </label>
            <textarea
              id="description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-black focus:outline-none focus:ring-black"
              placeholder="Analytics pipeline for customer data"
            />
          </div>

          <div>
            <label htmlFor="schedule_interval" className="block text-sm font-medium text-gray-700">
              Schedule Interval (Cron Expression)
            </label>
            <input
              type="text"
              id="schedule_interval"
              value={formData.schedule_interval}
              onChange={(e) => setFormData({ ...formData, schedule_interval: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-black focus:outline-none focus:ring-black"
              placeholder="0 6 * * *"
            />
            <p className="mt-1 text-sm text-gray-500">
              Example: "0 6 * * *" runs daily at 6 AM UTC, "0 */12 * * *" runs Every 12 hours
            </p>
          </div>

          <div>
            <label htmlFor="start_at" className="block text-sm font-medium text-gray-700">
              Start Date <span className="text-red-500">*</span>
            </label>
            <input
              type="datetime-local"
              id="start_at"
              value={formData.start_at}
              onChange={(e) => setFormData({ ...formData, start_at: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-black focus:outline-none focus:ring-black"
            />
            {errors.start_at && <p className="mt-1 text-sm text-red-600">{errors.start_at}</p>}
            <p className="mt-1 text-sm text-gray-500">Pipeline start time (immutable after creation)</p>
          </div>

          <div>
            <label htmlFor="type" className="block text-sm font-medium text-gray-700">
              Pipeline Type
            </label>
            <select
              id="type"
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-black focus:outline-none focus:ring-black"
            >
              <option value="dbt">DBT</option>
            </select>
          </div>

          <div className="flex gap-4">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 rounded-lg bg-black px-4 py-2 text-white hover:bg-gray-800 disabled:bg-gray-400"
            >
              {loading ? 'Creating...' : 'Create Pipeline'}
            </button>
            <button
              type="button"
              onClick={handleCancel}
              disabled={loading}
              className="flex-1 rounded-lg border border-gray-300 bg-white px-4 py-2 text-gray-700 hover:bg-gray-50 disabled:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreatePipeline;
