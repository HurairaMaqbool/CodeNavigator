import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function truncateId(id: string, max = 22): string {
  if (!id) return "";
  return id.length <= max ? id : `${id.slice(0, max)}…`;
}
