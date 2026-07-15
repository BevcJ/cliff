import * as PopoverPrimitive from "@radix-ui/react-popover";

import { cn } from "../../lib/utils";

export const Popover = PopoverPrimitive.Root;
export const PopoverAnchor = PopoverPrimitive.Anchor;
export const PopoverTrigger = PopoverPrimitive.Trigger;

export function PopoverContent({
  className,
  align = "start",
  sideOffset = 6,
  ...props
}: React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn("z-50 rounded-xl border bg-white p-2 shadow-md outline-none", className)}
        {...props}
      />
    </PopoverPrimitive.Portal>
  );
}
