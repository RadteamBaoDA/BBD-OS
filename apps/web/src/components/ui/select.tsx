"use client";

import * as React from 'react';
import { CheckIcon } from 'lucide-react';
import { Select as SelectPrimitive } from 'radix-ui';

export const Select = SelectPrimitive.Root;
export const SelectGroup = SelectPrimitive.Group;
export const SelectValue = SelectPrimitive.Value;
/** Renders the select trigger UI wrapper and forwards its typed props to the underlying control. */
export function SelectTrigger(props: React.ComponentProps<typeof SelectPrimitive.Trigger>) {
  return <SelectPrimitive.Trigger data-slot="select-trigger" {...props} className={`input ${props.className ?? ''}`} />;
}
/** Renders the select content UI wrapper and forwards its typed props to the underlying control. */
export function SelectContent({ children, ...props }: React.ComponentProps<typeof SelectPrimitive.Content>) {
  return <SelectPrimitive.Portal><SelectPrimitive.Content data-slot="select-content" {...props} className={`select-content ${props.className ?? ''}`}><SelectPrimitive.Viewport>{children}</SelectPrimitive.Viewport></SelectPrimitive.Content></SelectPrimitive.Portal>;
}
/** Renders the select item UI wrapper and forwards its typed props to the underlying control. */
export function SelectItem({ children, ...props }: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return <SelectPrimitive.Item data-slot="select-item" {...props} className={`select-item ${props.className ?? ''}`}><SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText><SelectPrimitive.ItemIndicator className="select-item-indicator"><CheckIcon size={14} /></SelectPrimitive.ItemIndicator></SelectPrimitive.Item>;
}
