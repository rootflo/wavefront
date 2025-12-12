import { TrashIcon } from 'lucide-react';
import React from 'react';

export interface ResourceCardMetadata {
  label: string;
  value: string;
  className?: string;
  isMono?: boolean;
}

interface ResourceCardProps {
  title: string;
  description?: string;
  metadata: ResourceCardMetadata[];
  onClick: () => void;
  onDeleteClick: (e: React.MouseEvent) => void;
  deleteTitle?: string;
}

const ResourceCard: React.FC<ResourceCardProps> = ({
  title,
  description,
  metadata,
  onClick,
  onDeleteClick,
  deleteTitle = 'Delete',
}) => {
  return (
    <div
      onClick={onClick}
      className="group cursor-pointer rounded-xl border-[0.5px] bg-white p-6 shadow-sm transition-all duration-500 hover:translate-y-[-4px] hover:shadow-md"
    >
      <div className="mb-3 flex items-start justify-between">
        <h3 className="overflow-hidden text-ellipsis pr-2 text-lg font-semibold text-gray-900 transition-colors group-hover:text-blue-500">
          {title}
        </h3>
        <div className="flex items-center space-x-2">
          <button
            onClick={onDeleteClick}
            className="cursor-pointer rounded p-1 text-red-500 opacity-0 transition-opacity hover:bg-red-50 hover:text-red-700 group-hover:opacity-100"
            title={deleteTitle}
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
      {description && <p className="mb-4 line-clamp-2 text-sm text-gray-600">{description}</p>}
      <div className="space-y-2">
        {metadata.map((item, index) => (
          <div key={index} className="flex items-center justify-between text-xs">
            <span className="font-medium text-gray-500">{item.label}</span>
            <span
              className={`rounded px-2 py-1 font-medium ${
                item.className || (item.isMono ? 'bg-gray-50 font-mono text-gray-700' : 'bg-gray-50 text-gray-700')
              }`}
            >
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

interface ResourceCardSkeletonProps {
  showDescription?: boolean;
  metadataCount?: number;
}

export const ResourceCardSkeleton: React.FC<ResourceCardSkeletonProps> = ({
  showDescription = false,
  metadataCount = 2,
}) => {
  return (
    <div className="animate-fade-in rounded-xl bg-white p-6 shadow-sm">
      <div className="mb-3 flex items-start justify-between">
        <div className="h-6 w-32 animate-pulse rounded bg-gray-200"></div>
        <div className="flex items-center space-x-2">
          <div className="h-4 w-4 rounded bg-gray-200"></div>
          <div className="h-5 w-5 rounded bg-gray-200"></div>
        </div>
      </div>
      {showDescription && (
        <div className="mb-4 space-y-2">
          <div className="h-4 w-full animate-pulse rounded bg-gray-200"></div>
          <div className="h-4 w-3/4 animate-pulse rounded bg-gray-200"></div>
        </div>
      )}
      <div className="space-y-2">
        {Array.from({ length: metadataCount }).map((_, index) => (
          <div key={index} className="flex items-center justify-between text-xs">
            <div className="h-3 w-16 animate-pulse rounded bg-gray-200"></div>
            <div className="h-5 w-20 animate-pulse rounded bg-gray-200"></div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ResourceCard;
