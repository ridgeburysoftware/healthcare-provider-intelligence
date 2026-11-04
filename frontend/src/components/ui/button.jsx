import {Slot} from '@radix-ui/react-slot';
import {clsx} from 'clsx';
import {twMerge} from 'tailwind-merge';
export function Button({className,variant='default',asChild=false,...props}){
 const Component=asChild?Slot:'button';
 return <Component className={twMerge(clsx('inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 disabled:pointer-events-none disabled:opacity-50',variant==='default'?'bg-teal-700 text-white hover:bg-teal-800':'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',className))} {...props}/>;
}
