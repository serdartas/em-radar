// SPDX-License-Identifier: Apache-2.0

import { NavLink, Outlet } from "react-router-dom"

import { Logo } from "@/components/Logo"
import { navItems } from "@/lib/navigation"
import { cn } from "@/lib/utils"
import { loadWizardProgress } from "@/lib/wizardProgress"

function PrimaryNav() {
  const wizardCompleted = loadWizardProgress()?.completed === true
  const visibleItems = wizardCompleted ? navItems.filter(({ to }) => to !== "/setup") : navItems

  return (
    <nav aria-label="Primary" className="p-3">
      <ul className="flex flex-wrap gap-1 md:flex-col">
        {visibleItems.map(({ to, label, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-slate-600 hover:bg-primary/10 hover:text-foreground",
                )
              }
              end={end}
              to={to}
            >
              <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}

export function AppLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-foreground">
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        href="#main-content"
      >
        Skip to content
      </a>

      <header className="flex h-14 shrink-0 items-center border-b bg-white px-4 md:px-8">
        <NavLink className="flex items-center gap-2.5" to="/">
          <Logo className="h-7 w-7 shrink-0" />
          <span className="text-base font-semibold tracking-tight">EM Radar</span>
          <span className="hidden text-xs text-slate-500 sm:inline">
            Engineering management signals
          </span>
        </NavLink>
      </header>

      <div className="flex flex-1 flex-col md:flex-row">
        <aside className="shrink-0 border-b bg-white md:w-64 md:border-b-0 md:border-r">
          <PrimaryNav />
        </aside>

        <main className="min-w-0 flex-1 px-4 py-8 md:px-8" id="main-content">
          <div className="mx-auto w-full max-w-5xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
