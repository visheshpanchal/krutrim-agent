import { cn, useTheme } from "@krutrim_agent/ui";
import { Moon, Sun } from "lucide-react";



function AppearanceControl() {
  const { theme, toggleTheme } = useTheme();
  const options: { value: 'light' | 'dark'; label: string; icon: typeof Sun }[] = [
    { value: 'light', label: 'Light', icon: Sun },
    { value: 'dark', label: 'Dark', icon: Moon },
  ];

  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-foreground">Appearance</span>
      <div className="flex rounded-md border border-border p-0.5">
        {options.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => theme !== value && toggleTheme()}
            aria-pressed={theme === value}
            className={cn(
              'flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors',
              theme === value ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="size-3" />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default AppearanceControl;