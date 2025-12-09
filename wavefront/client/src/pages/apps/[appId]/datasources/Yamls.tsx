import { Button } from '@app/components/ui/button';
import { Yaml } from '@app/types/datasource';
import { EditIcon } from 'lucide-react';

const Yamls = ({
  yamls,
  setYamlCrud,
  setSelectedYaml,
}: {
  yamls: Yaml[];
  setYamlCrud: React.Dispatch<
    React.SetStateAction<{ view: boolean; edit: boolean; create: boolean; delete: boolean; execute: boolean }>
  >;
  setSelectedYaml: React.Dispatch<React.SetStateAction<string | null>>;
}) => {
  const setOnly = (
    key: keyof { view: boolean; edit: boolean; create: boolean; delete: boolean; execute: boolean },
    file_path: string
  ) => {
    setYamlCrud({
      view: false,
      edit: false,
      create: false,
      delete: false,
      execute: false,
      [key]: true,
    });
    setSelectedYaml(file_path);
  };

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-[#EFF0F1] bg-[#FBFBFB] p-6">
      <div className="grid w-full grid-cols-4 rounded-lg border border-[#EFF0F1] bg-white p-4">
        <div className="text-base font-medium text-[#282828]">Version</div>
        <div className="text-base font-medium text-[#282828]">File</div>
        <div className="text-center text-base font-medium text-[#282828]">Actions</div>
        <div></div>
      </div>
      {yamls.map((yaml) => (
        <div
          key={yaml.full_path}
          className="grid w-full cursor-pointer grid-cols-4 items-center rounded-lg border border-[#EFF0F1] bg-white p-4 transition-colors duration-200 hover:bg-[#F7FAFF]"
          onClick={() => setOnly('view', yaml.file)}
        >
          <div className="text-sm font-normal text-[#282828]">{yaml.version}</div>
          <div className="text-sm font-normal text-[#282828]">{yaml.file}</div>
          <div className="flex items-center justify-center gap-2">
            <Button
              className="h-max w-max cursor-pointer rounded-full !bg-transparent p-2 text-sm font-normal !text-black transition-colors duration-200 hover:!bg-black hover:!text-white"
              onClick={(e) => {
                e.stopPropagation();
                setOnly('edit', yaml.file);
              }}
            >
              <EditIcon height={16} width={16} />
            </Button>
            <Button
              className="h-max w-max cursor-pointer rounded-full !bg-transparent p-2 text-sm font-normal !text-[#E22F2F] transition-colors duration-200 hover:!bg-[#E22F2F] hover:!text-white"
              onClick={(e) => {
                e.stopPropagation();
                setOnly('delete', yaml.file);
              }}
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </Button>
          </div>
          <div className="flex justify-end">
            <Button
              onClick={(e) => {
                e.stopPropagation();
                setOnly('execute', yaml.file);
              }}
            >
              Execute
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
};
export default Yamls;
