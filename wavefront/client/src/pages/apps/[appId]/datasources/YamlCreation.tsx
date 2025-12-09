import { Button } from "@app/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@app/components/ui/dialog";
import { validateDynamicQueryYaml } from "@app/lib/utils";
import { langs } from "@uiw/codemirror-extensions-langs";
import CodeMirror from "@uiw/react-codemirror";
import clsx from "clsx";
import { useState } from "react";

interface YamlCreationProps {
  yamlContent: string;
  setYamlContent: React.Dispatch<React.SetStateAction<string>>;
  yamlCreation: boolean;
  setYamlCreation: React.Dispatch<React.SetStateAction<boolean>>;
  createYaml: () => void;
}

const YamlCreation: React.FC<YamlCreationProps> = ({
  yamlContent,
  setYamlContent,
  yamlCreation,
  setYamlCreation,
  createYaml,
}) => {
  const [error, setError] = useState<string>("");
  const [isCreating, setIsCreating] = useState<boolean>(false);

  const handleSubmit = (yamlContent: string) => {
    // build the yaml content
    const response: { valid: boolean; error: string } =
      validateDynamicQueryYaml(yamlContent);
    if (response.valid) {
      setIsCreating(true);
      createYaml();
    } else {
      setError(response.error);
    }
  };
  const handleClose = () => {
    setYamlContent("");
    setYamlCreation(false);
    setError("");
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && !isCreating) {
      handleClose();
    }
  };

  return (
    <Dialog open={yamlCreation} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[90vh] min-w-[800px] max-w-[800px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add YAML</DialogTitle>
          <DialogDescription>
            Define your YAML configuration for the datasource query.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <CodeMirror
            className="w-full overflow-hidden rounded-xl border border-[#EFF0F1] bg-white p-4 font-mono text-sm font-normal text-[#282828] outline-none"
            value={yamlContent}
            height="500px"
            extensions={[langs.yaml()]}
            onChange={(value: string) => setYamlContent(value)}
            theme="dark"
          />
        </div>

        <p
          className={clsx(
            "min-h-4 text-sm text-red-500 transition-opacity duration-200",
            error ? "opacity-100" : "opacity-0"
          )}
        >
          {error}
        </p>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isCreating}>
            Cancel
          </Button>
          <Button
            onClick={() => handleSubmit(yamlContent)}
            disabled={isCreating}
            loading={isCreating}
          >
            {isCreating ? "Creating..." : "Create YAML"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
export default YamlCreation;
