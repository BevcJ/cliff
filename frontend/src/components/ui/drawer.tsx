import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { cn } from "../../lib/utils";
import { Button } from "./button";

type DrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
};

export function Drawer({ open, onOpenChange, title, children }: DrawerProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-foreground/20" />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 z-50 h-screen w-[520px] max-w-[calc(100vw-80px)] overflow-y-auto border-l bg-white shadow-xl",
          )}
        >
          <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-white px-5 py-4">
            <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <Button aria-label="Close detail drawer" size="sm" variant="ghost">
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>
          <div className="p-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
