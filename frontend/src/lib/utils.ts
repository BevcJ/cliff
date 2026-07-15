import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function compact(value: string | null | undefined) {
  return (value ?? "").trim();
}

export function formatCount(value: number | null | undefined) {
  return new Intl.NumberFormat("en").format(value ?? 0);
}
