import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap",
    "text-sm font-medium transition-all duration-150 ease-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-45",
    "active:scale-[0.98]",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "rounded-lg bg-primary text-primary-foreground shadow-elev-1 hover:bg-primary-hover hover:shadow-elev-2",
        secondary:
          "rounded-lg border border-border bg-surface-raised text-foreground hover:bg-surface-hover hover:border-border-strong",
        ghost:
          "rounded-lg text-muted-foreground hover:bg-surface-hover hover:text-foreground",
        destructive:
          "rounded-lg bg-error/15 text-error border border-error/25 hover:bg-error/20",
        outline:
          "rounded-lg border border-border bg-transparent text-foreground hover:bg-surface-hover hover:border-border-strong",
      },
      size: {
        default: "min-h-[40px] px-4 py-2",
        sm: "min-h-[32px] rounded-md px-3 text-xs",
        lg: "min-h-[44px] rounded-lg px-5 text-[15px]",
        icon: "h-10 w-10 rounded-lg",
        "icon-sm": "h-8 w-8 rounded-md",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
