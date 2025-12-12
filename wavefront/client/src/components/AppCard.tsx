import { App } from "@app/types/app";
import { Pencil, Trash2 } from "lucide-react";
import React from "react";
import { useNavigate } from "react-router";
import dayjs from "dayjs";

interface AppCardProps {
  app: App;
  onClick: (app: App) => void;
  onDeleteClick: (app: App) => void;
}

const AppCard: React.FC<AppCardProps> = ({ app, onClick, onDeleteClick }) => {
  const navigate = useNavigate();

  const handleEditApp = (app: App) => {
    navigate(`/apps/edit/${app.id}`);
  };

  return (
    <div
      className="group relative flex  w-full cursor-pointer flex-col gap-8 rounded-xl border border-[#FFF] bg-white/60 p-5"
      onClick={(e) => {
        e.preventDefault();
        onClick(app);
      }}
    >
      <div className="absolute right-5 top-5 flex items-center gap-2">
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleEditApp(app);
          }}
          className="cursor-pointer rounded p-1 text-gray-600 opacity-0 transition-opacity hover:bg-gray-100 hover:text-gray-900 group-hover:opacity-100"
          title="Edit"
        >
          <Pencil className="h-4 w-4" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDeleteClick(app);
          }}
          className="cursor-pointer rounded p-1 text-red-500 opacity-0 transition-opacity hover:bg-red-50 hover:text-red-700 group-hover:opacity-100"
          title="Delete"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      <div>
        <p className="text-xl font-medium text-[#101010]">{app.app_name}</p>
        <p className="text-base font-normal text-[#878787] truncate">
          {app.public_url}
        </p>
      </div>
      <div className="text-sm font-normal text-[#B8B8B8]">
        {dayjs(app.updated_at).format("DD MMM YYYY")}
      </div>
    </div>
  );
};

export default AppCard;
