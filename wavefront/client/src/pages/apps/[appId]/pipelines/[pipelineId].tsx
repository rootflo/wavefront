import floConsoleService from '@app/api';
import { useGetPipeline, useGetPipelineFiles } from '@app/hooks/data/fetch-hooks';
import { useNotifyStore } from '@app/store';
import { FileType, PipelineFile } from '@app/types/pipeline';
import { useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import React, { useState } from 'react';
import { useNavigate, useParams } from 'react-router';

const PipelineDetail: React.FC = () => {
  const { app, pipelineId } = useParams<{ app: string; pipelineId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notifySuccess, notifyError } = useNotifyStore();

  const pipelineService = floConsoleService.dataPipelineService;
  const fileService = floConsoleService.dataPipelineService;

  const [selectedFile, setSelectedFile] = useState<PipelineFile | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [isEditing, setIsEditing] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);

  // Create file modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newFilePath, setNewFilePath] = useState('');
  const [newFileContent, setNewFileContent] = useState('');
  const [createLoading, setCreateLoading] = useState(false);
  const [filePathError, setFilePathError] = useState('');

  // Delete file state
  const [fileToDelete, setFileToDelete] = useState<PipelineFile | null>(null);

  // Action loading states
  const [publishLoading, setPublishLoading] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [triggerLoading, setTriggerLoading] = useState(false);

  // Schedule edit state
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleValue, setScheduleValue] = useState('');
  const [scheduleLoading, setScheduleLoading] = useState(false);

  // Fetch pipeline details
  const { data: pipeline, isLoading: pipelineLoading, error: pipelineError } = useGetPipeline(app, pipelineId);

  // Fetch files
  const { data: files = [], isLoading: filesLoading } = useGetPipelineFiles(app, pipelineId);

  const handlePublish = async () => {
    if (!pipeline || publishLoading) return;
    setPublishLoading(true);
    try {
      await pipelineService.publishPipeline('default', pipeline.pipeline_id);
      notifySuccess('Pipeline published successfully');
      queryClient.invalidateQueries({ queryKey: ['pipeline', app, pipelineId] });
    } catch (error: any) {
      notifyError(error?.response?.data?.error?.message || 'Failed to publish pipeline');
    } finally {
      setPublishLoading(false);
    }
  };

  const handlePause = async () => {
    if (!pipeline || pauseLoading) return;
    setPauseLoading(true);
    try {
      if (pipeline.status === 'published') {
        await pipelineService.pausePipeline('default', pipeline.pipeline_id);
        notifySuccess('Pipeline paused successfully');
      } else if (pipeline.status === 'paused') {
        await pipelineService.unpausePipeline('default', pipeline.pipeline_id);
        notifySuccess('Pipeline unpaused successfully');
      }
      queryClient.invalidateQueries({ queryKey: ['pipeline', app, pipelineId] });
    } catch (error) {
      notifyError('Failed to update pipeline status');
    } finally {
      setPauseLoading(false);
    }
  };

  const handleTrigger = async () => {
    if (!pipeline || triggerLoading) return;
    setTriggerLoading(true);
    try {
      await pipelineService.triggerDagRun('default', pipeline.pipeline_id);
      notifySuccess('Pipeline triggered successfully');
    } catch (error) {
      notifyError('Failed to trigger pipeline');
    } finally {
      setTriggerLoading(false);
    }
  };

  const handleFileClick = async (file: PipelineFile) => {
    try {
      const response = await fileService.getFileContent(pipelineId!, file.path);
      setSelectedFile(file);
      setFileContent(response.data?.data?.content || '');
      setIsEditing(false);
    } catch (error) {
      notifyError('Failed to load file content');
    }
  };

  const handleSaveFile = async () => {
    if (!selectedFile) return;
    setSaveLoading(true);
    try {
      await fileService.updateFile(pipelineId!, selectedFile.path, fileContent);
      notifySuccess('File saved successfully');
      setIsEditing(false);
      queryClient.invalidateQueries({ queryKey: ['pipeline-files', app, pipelineId] });
    } catch (error) {
      notifyError('Failed to save file');
    } finally {
      setSaveLoading(false);
    }
  };

  const validateFilePath = (path: string): string | null => {
    if (!path.trim()) {
      return 'File path is required';
    }
    if (path.includes('..')) {
      return 'Directory traversal not allowed';
    }
    if (path.startsWith('/')) {
      return 'Absolute paths not allowed';
    }
    const validExtensions = ['.sql', '.yml', '.yaml', '.md'];
    const hasValidExtension = validExtensions.some((ext) => path.endsWith(ext));
    if (!hasValidExtension) {
      return 'File must end with .sql, .yml, .yaml, or .md';
    }
    return null;
  };

  const handleCreateFile = async () => {
    const error = validateFilePath(newFilePath);
    if (error) {
      setFilePathError(error);
      return;
    }

    setCreateLoading(true);
    try {
      await fileService.createFile(pipelineId!, newFilePath, newFileContent);
      notifySuccess('File created successfully');
      setShowCreateModal(false);
      setNewFilePath('');
      setNewFileContent('');
      setFilePathError('');
      queryClient.invalidateQueries({ queryKey: ['pipeline-files', app, pipelineId] });

      // Optionally load the new file
      setTimeout(async () => {
        const response = await fileService.getFileContent(pipelineId!, newFilePath);
        if (response.data?.data) {
          const file: PipelineFile = {
            path: newFilePath,
            type: response.data.data.type,
            size: response.data.data.size,
          };
          setSelectedFile(file);
          setFileContent(response.data.data.content);
          setIsEditing(false);
        }
      }, 500);
    } catch (error: any) {
      const errorMsg = error?.response?.data?.error?.message || 'Failed to create file';
      notifyError(errorMsg);
      setFilePathError(errorMsg);
    } finally {
      setCreateLoading(false);
    }
  };

  const handleDeleteFile = async () => {
    if (!fileToDelete) return;

    try {
      await fileService.deleteFile(pipelineId!, fileToDelete.path);
      notifySuccess('File deleted successfully');

      // Clear selection if deleted file was selected
      if (selectedFile?.path === fileToDelete.path) {
        setSelectedFile(null);
        setFileContent('');
        setIsEditing(false);
      }

      setFileToDelete(null);
      queryClient.invalidateQueries({ queryKey: ['pipeline-files', app, pipelineId] });
    } catch (error) {
      notifyError('Failed to delete file');
    }
  };

  const handleOpenScheduleModal = () => {
    setScheduleValue(pipeline?.schedule_interval || '');
    setShowScheduleModal(true);
  };

  const handleUpdateSchedule = async () => {
    if (!pipeline) return;
    setScheduleLoading(true);
    try {
      await pipelineService.updateSchedule(pipeline.pipeline_id, {
        schedule_interval: scheduleValue.trim() || null,
      });
      notifySuccess('Schedule updated successfully');
      setShowScheduleModal(false);
      queryClient.invalidateQueries({ queryKey: ['pipeline', app, pipelineId] });
    } catch (error: any) {
      notifyError(error?.response?.data?.error?.message || 'Failed to update schedule');
    } finally {
      setScheduleLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
      draft: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Draft' },
      published: { bg: 'bg-green-100', text: 'text-green-800', label: 'Published' },
      paused: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Paused' },
    };

    const config = statusConfig[status] || statusConfig.draft;
    return (
      <span className={clsx('rounded-full px-3 py-1 text-xs font-medium', config.bg, config.text)}>{config.label}</span>
    );
  };

  const getFileIcon = (type: FileType) => {
    const icons: Record<FileType, string> = {
      model: '📊',
      test: '✓',
      macro: '🔧',
      config: '⚙️',
      schema: '📋',
      doc: '📄',
      other: '📁',
    };
    return icons[type] || icons.other;
  };

  // Build tree structure from file paths
  interface TreeNode {
    name: string;
    path: string;
    isDirectory: boolean;
    file?: PipelineFile;
    children: TreeNode[];
  }

  const buildFileTree = (files: PipelineFile[]): TreeNode[] => {
    const root: TreeNode[] = [];

    files.forEach((file) => {
      const parts = file.path.split('/');
      let currentLevel = root;

      parts.forEach((part, index) => {
        const isLastPart = index === parts.length - 1;
        const existingNode = currentLevel.find((node) => node.name === part);

        if (existingNode) {
          if (!isLastPart) {
            currentLevel = existingNode.children;
          }
        } else {
          const newNode: TreeNode = {
            name: part,
            path: parts.slice(0, index + 1).join('/'),
            isDirectory: !isLastPart,
            file: isLastPart ? file : undefined,
            children: [],
          };
          currentLevel.push(newNode);
          if (!isLastPart) {
            currentLevel = newNode.children;
          }
        }
      });
    });

    return root;
  };

  const fileTree = buildFileTree(files);

  // Component for rendering tree nodes
  const TreeNodeComponent: React.FC<{ node: TreeNode; level: number }> = ({ node, level }) => {
    const [isExpanded, setIsExpanded] = useState(true);
    const [showMenu, setShowMenu] = useState(false);

    if (node.isDirectory) {
      return (
        <div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex w-full items-center gap-1 rounded px-2 py-1 text-left text-sm hover:bg-gray-100"
            style={{ paddingLeft: `${level * 12 + 8}px` }}
          >
            <span className="text-xs">{isExpanded ? '▼' : '▶'}</span>
            <span>📁 {node.name}/</span>
          </button>
          {isExpanded && (
            <div>
              {node.children.map((child) => (
                <TreeNodeComponent key={child.path} node={child} level={level + 1} />
              ))}
            </div>
          )}
        </div>
      );
    }

    return (
      <div className="group relative">
        <button
          onClick={() => node.file && handleFileClick(node.file)}
          className={clsx(
            'flex w-full items-center justify-between gap-1 rounded px-2 py-1 text-left text-sm hover:bg-gray-100',
            selectedFile?.path === node.path && 'bg-gray-100'
          )}
          style={{ paddingLeft: `${level * 12 + 8}px` }}
        >
          <div className="flex items-center gap-1">
            <span>{node.file ? getFileIcon(node.file.type) : '📄'}</span>
            <span>{node.name}</span>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowMenu(!showMenu);
            }}
            className="rounded px-1 opacity-0 group-hover:opacity-100 hover:bg-gray-200"
          >
            ⋮
          </button>
        </button>
        {showMenu && (
          <div className="absolute top-8 right-2 z-10 rounded border border-gray-200 bg-white shadow-lg">
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (node.file) {
                  setFileToDelete(node.file);
                }
                setShowMenu(false);
              }}
              className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-gray-100"
            >
              Delete
            </button>
          </div>
        )}
      </div>
    );
  };

  if (pipelineLoading) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="flex justify-center">
          <div className="text-gray-500">Loading pipeline...</div>
        </div>
      </div>
    );
  }

  if (pipelineError || !pipeline) {
    return (
      <div className="min-h-screen bg-white p-6">
        <div className="flex justify-center">
          <div className="text-red-500">Error loading pipeline. Please try again.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white">
      {/* Left sidebar - File browser */}
      <div className="w-80 overflow-y-auto border-r border-gray-200">
        <div className="p-4">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Files</h2>
            <button
              onClick={() => setShowCreateModal(true)}
              className="rounded-lg bg-black px-3 py-1 text-sm text-white hover:bg-gray-800"
            >
              + New File
            </button>
          </div>
          {filesLoading ? (
            <div className="mt-4 text-sm text-gray-500">Loading files...</div>
          ) : (
            <div className="space-y-1">
              {fileTree.map((node) => (
                <TreeNodeComponent key={node.path} node={node} level={0} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <div className="border-b border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">{pipeline.project_name}</h1>
              {pipeline.description && <p className="mt-1 text-gray-600">{pipeline.description}</p>}
              <div className="mt-2 flex items-center gap-4">
                {getStatusBadge(pipeline.status)}
                <div className="flex items-center gap-2">
                  {pipeline.schedule_interval ? (
                    <span className="text-sm text-gray-600">Schedule: {pipeline.schedule_interval}</span>
                  ) : (
                    <span className="text-sm text-gray-500">No schedule set</span>
                  )}
                  <button
                    onClick={handleOpenScheduleModal}
                    className="text-sm text-blue-600 underline hover:text-blue-800"
                  >
                    Edit Schedule
                  </button>
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              {/* Publish/Republish button - always visible */}
              <button
                onClick={handlePublish}
                disabled={publishLoading}
                className="rounded-lg bg-black px-4 py-2 text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:bg-gray-400"
              >
                {publishLoading ? 'Publishing...' : pipeline.status === 'draft' ? 'Publish' : 'Republish'}
              </button>

              {/* Pause/Unpause button - for published and paused statuses */}
              {(pipeline.status === 'published' || pipeline.status === 'paused') && (
                <button
                  onClick={handlePause}
                  disabled={pauseLoading}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-100"
                >
                  {pauseLoading
                    ? pipeline.status === 'published'
                      ? 'Pausing...'
                      : 'Unpausing...'
                    : pipeline.status === 'published'
                      ? 'Pause'
                      : 'Unpause'}
                </button>
              )}

              {/* Trigger button - only for published status */}
              {pipeline.status === 'published' && (
                <button
                  onClick={handleTrigger}
                  disabled={triggerLoading}
                  className="rounded-lg bg-black px-4 py-2 text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:bg-gray-400"
                >
                  {triggerLoading ? 'Triggering...' : 'Trigger'}
                </button>
              )}

              <button
                onClick={() => navigate(`/apps/${app}/data-pipelines`)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
              >
                Back
              </button>
            </div>
          </div>
        </div>

        {/* File editor */}
        <div className="flex-1 overflow-hidden">
          {selectedFile ? (
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-gray-200 p-4">
                <h3 className="text-sm font-medium text-gray-900">{selectedFile.path}</h3>
                <div className="flex gap-2">
                  {!isEditing ? (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800"
                    >
                      Edit
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={handleSaveFile}
                        disabled={saveLoading}
                        className="rounded-lg bg-black px-4 py-2 text-sm text-white hover:bg-gray-800 disabled:bg-gray-400"
                      >
                        {saveLoading ? 'Saving...' : 'Save'}
                      </button>
                      <button
                        onClick={() => setIsEditing(false)}
                        disabled={saveLoading}
                        className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-auto p-4">
                {isEditing ? (
                  <textarea
                    value={fileContent}
                    onChange={(e) => setFileContent(e.target.value)}
                    className="h-full w-full rounded border border-gray-300 p-4 font-mono text-sm focus:ring-2 focus:ring-black focus:outline-none"
                  />
                ) : (
                  <pre className="font-mono text-sm whitespace-pre-wrap">{fileContent}</pre>
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-gray-500">Select a file to view or edit</div>
          )}
        </div>
      </div>

      {/* Create File Modal */}
      {showCreateModal && (
        <div className="bg-opacity-50 fixed inset-0 z-50 flex items-center justify-center bg-black">
          <div className="w-full max-w-2xl rounded-lg bg-white p-6">
            <h2 className="mb-4 text-xl font-bold text-gray-900">Create New File</h2>
            <div className="space-y-4">
              <div>
                <label htmlFor="file-path" className="mb-1 block text-sm font-medium text-gray-700">
                  File Path
                </label>
                <input
                  id="file-path"
                  type="text"
                  value={newFilePath}
                  onChange={(e) => {
                    setNewFilePath(e.target.value);
                    setFilePathError('');
                  }}
                  placeholder="models/staging/new_model.sql or tests/test_data.sql"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-black focus:ring-1 focus:ring-black focus:outline-none"
                />
                {filePathError && <p className="mt-1 text-sm text-red-600">{filePathError}</p>}
                <p className="mt-1 text-sm text-gray-500">
                  Supported extensions: .sql, .yml, .yaml, .md. Directories will be created automatically.
                </p>
              </div>
              <div>
                <label htmlFor="file-content" className="mb-1 block text-sm font-medium text-gray-700">
                  Initial Content (Optional)
                </label>
                <textarea
                  id="file-content"
                  value={newFileContent}
                  onChange={(e) => setNewFileContent(e.target.value)}
                  rows={10}
                  placeholder="-- New DBT model&#10;&#10;SELECT * FROM {{ ref('source_table') }}"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:border-black focus:ring-1 focus:ring-black focus:outline-none"
                />
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowCreateModal(false);
                    setNewFilePath('');
                    setNewFileContent('');
                    setFilePathError('');
                  }}
                  disabled={createLoading}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateFile}
                  disabled={createLoading}
                  className="rounded-lg bg-black px-4 py-2 text-white hover:bg-gray-800 disabled:bg-gray-400"
                >
                  {createLoading ? 'Creating...' : 'Create File'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete File Confirmation */}
      {fileToDelete && (
        <div className="bg-opacity-50 fixed inset-0 z-50 flex items-center justify-center bg-black">
          <div className="w-full max-w-md rounded-lg bg-white p-6">
            <h2 className="mb-4 text-xl font-bold text-gray-900">Delete File</h2>
            <p className="mb-6 text-gray-600">
              Are you sure you want to delete <strong>{fileToDelete.path}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setFileToDelete(null)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteFile}
                className="rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Schedule Modal */}
      {showScheduleModal && (
        <div className="bg-opacity-50 fixed inset-0 z-50 flex items-center justify-center bg-black">
          <div className="w-full max-w-md rounded-lg bg-white p-6">
            <h2 className="mb-4 text-xl font-bold text-gray-900">Edit Schedule</h2>
            <div className="space-y-4">
              <div>
                <label htmlFor="schedule-interval" className="mb-1 block text-sm font-medium text-gray-700">
                  Schedule Interval (Cron Expression)
                </label>
                <input
                  id="schedule-interval"
                  type="text"
                  value={scheduleValue}
                  onChange={(e) => setScheduleValue(e.target.value)}
                  placeholder="0 6 * * *"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 focus:border-black focus:ring-1 focus:ring-black focus:outline-none"
                />
                <div className="mt-2 space-y-1 text-sm text-gray-500">
                  <p>Examples:</p>
                  <p>
                    • <code className="rounded bg-gray-100 px-1">0 6 * * *</code> - Daily at 6 AM UTC
                  </p>
                  <p>
                    • <code className="rounded bg-gray-100 px-1">0 */12 * * *</code> - Every 12 hours
                  </p>
                  <p>
                    • <code className="rounded bg-gray-100 px-1">0 0 * * 0</code> - Every Sunday at midnight
                  </p>
                  <p className="mt-2">Leave empty to disable scheduling</p>
                </div>
              </div>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowScheduleModal(false);
                    setScheduleValue('');
                  }}
                  disabled={scheduleLoading}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpdateSchedule}
                  disabled={scheduleLoading}
                  className="rounded-lg bg-black px-4 py-2 text-white hover:bg-gray-800 disabled:bg-gray-400"
                >
                  {scheduleLoading ? 'Saving...' : 'Save Schedule'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PipelineDetail;
