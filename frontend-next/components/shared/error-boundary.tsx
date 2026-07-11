"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

type Props = { children: ReactNode; title?: string };
type State = { hasError: boolean; error?: Error };

export class PanelErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (process.env.NODE_ENV === "development") {
      console.error("Panel error:", error, info);
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="rounded-xl border border-warning/40 bg-warning/10 p-6 text-center"
          role="alert"
        >
          <AlertTriangle className="mx-auto h-8 w-8 text-warning" />
          <p className="mt-3 font-medium text-foreground">
            {this.props.title ?? "Something went wrong in this panel"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={() => this.setState({ hasError: false, error: undefined })}
          >
            Try again
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}
