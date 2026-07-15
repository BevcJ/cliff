import { DayPicker } from "react-day-picker";

import { cn } from "../../lib/utils";

export function Calendar({ className, ...props }: React.ComponentProps<typeof DayPicker>) {
  return <DayPicker className={cn("rounded-xl bg-white p-3 text-sm", className)} {...props} />;
}
