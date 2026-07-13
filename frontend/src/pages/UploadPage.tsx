import { FileSpreadsheet, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useUpload } from "@/hooks/useDatasets";

/** Drag-and-drop dataset upload page. */
export function UploadPage() {
  const navigate = useNavigate();
  const upload = useUpload();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = async (file: File) => {
    const summary = await upload.mutateAsync(file);
    navigate(`/datasets/${summary.id}`);
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Upload dataset</h1>
        <p className="text-muted-foreground">Supported formats: CSV, Excel (.xlsx), JSON. Max 50 MB.</p>
      </div>

      <Card>
        <CardContent className="pt-5">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
            }}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-12 text-center transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
            )}
          >
            <div className="flex size-14 items-center justify-center rounded-full bg-primary/10 text-primary">
              <UploadCloud className="size-7" />
            </div>
            <div>
              <p className="font-medium">
                {upload.isPending ? "Uploading & profiling…" : "Drag & drop your file here"}
              </p>
              <p className="text-sm text-muted-foreground">or click to browse</p>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xls,.json"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
            />
          </div>

          <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
            <FileSpreadsheet className="size-4" />
            Files are profiled automatically on upload — encoding, delimiter and column types are detected.
          </div>
          {upload.isPending && (
            <Button variant="gradient" className="mt-4 w-full" disabled>
              Processing…
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
