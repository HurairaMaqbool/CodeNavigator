import { AlertCircle, AlertTriangle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

type AlertKind = "error" | "warning" | "info" | "success";

const icons: Record<AlertKind, React.ReactNode> = {
  error: <AlertCircle className="h-4 w-4 shrink-0" aria-hidden />,
  warning: <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />,
  info: <Info className="h-4 w-4 shrink-0" aria-hidden />,
  success: <Info className="h-4 w-4 shrink-0" aria-hidden />,
};

const styles: Record<AlertKind, string> = {
  error: "border-error/30 bg-error/10 text-error",
  warning: "border-warning/30 bg-warning/10 text-warning",
  info: "border-info/30 bg-info/10 text-info",
  success: "border-success/30 bg-success/10 text-success",
};

export function Alert({
  kind,
  children,
  className,
}: {
  kind: AlertKind;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 rounded-lg border px-4 py-3 text-sm",
        styles[kind],
        className,
      )}
    >
      {icons[kind]}
      <span>{children}</span>
    </div>
  );
}
