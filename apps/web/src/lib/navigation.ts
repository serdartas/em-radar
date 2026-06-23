import {
  FileText,
  Layers,
  LayoutDashboard,
  type LucideIcon,
  Play,
  Plug,
  Rocket,
  Settings,
  SlidersHorizontal,
  Users,
} from "lucide-react"

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

export const navItems: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/setup", label: "Setup", icon: Rocket },
  { to: "/connections", label: "Source Connections", icon: Plug },
  { to: "/teams", label: "Teams", icon: Users },
  { to: "/signals", label: "Signal Settings", icon: SlidersHorizontal },
  { to: "/signals/groups", label: "Signal Config Groups", icon: Layers },
  { to: "/reports/run", label: "Report Runner", icon: Play },
  { to: "/reports/results", label: "Report Results", icon: FileText },
  { to: "/settings", label: "Settings & Privacy", icon: Settings },
]
