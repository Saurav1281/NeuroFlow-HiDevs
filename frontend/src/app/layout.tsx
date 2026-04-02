"use client";

import { Inter, Outfit } from "next/font/google";
import "./globals.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import Link from "next/link";
import { LayoutDashboard, PlayCircle, Activity, FileText, Settings, Zap } from "lucide-react";
import { cn } from "@/utils/cn";
import { usePathname } from "next/navigation";

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [queryClient] = useState(() => new QueryClient());
  const pathname = usePathname();

  const navItems = [
    { name: "Playground", href: "/playground", icon: PlayCircle },
    { name: "Pipelines", href: "/pipelines", icon: Zap },
    { name: "Evaluations", href: "/evaluations", icon: Activity },
    { name: "Documents", href: "/documents", icon: FileText },
  ];

  return (
    <html lang="en" className={cn(outfit.variable, inter.variable, "dark")}>
      <body className="font-sans antialiased text-white bg-[#030303]">
        <QueryClientProvider client={queryClient}>
          <div className="flex h-screen overflow-hidden">
            {/* Sidebar */}
            <aside className="w-64 border-r border-white/10 bg-[#0a0a0f] flex flex-col">
              <div className="p-6 flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg premium-gradient flex items-center justify-center">
                  <Zap className="w-5 h-5 text-white" fill="white" />
                </div>
                <h1 className="text-xl font-bold tracking-tight">NeuroFlow</h1>
              </div>
              
              <nav className="flex-1 px-4 space-y-2 py-4">
                {navItems.map((item) => (
                  <Link
                    key={item.name}
                    href={item.name.toLowerCase() === "playground" ? "/playground" : item.href}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group",
                      pathname.startsWith(item.href) 
                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/20" 
                        : "text-zinc-400 hover:text-white hover:bg-white/5"
                    )}
                  >
                    <item.icon className={cn(
                      "w-5 h-5 transition-colors",
                      pathname.startsWith(item.href) ? "text-blue-400" : "text-zinc-500 group-hover:text-zinc-300"
                    )} />
                    <span className="font-medium">{item.name}</span>
                  </Link>
                ))}
              </nav>

              <div className="p-4 mt-auto">
                <div className="glass-card p-4 rounded-xl bg-gradient-to-br from-white/5 to-transparent">
                  <p className="text-xs text-zinc-500 mb-2 uppercase tracking-widest font-bold">System Status</p>
                  <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <span className="text-sm font-medium">All Systems Operational</span>
                  </div>
                </div>
              </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-blue-900/10 via-transparent to-transparent">
              {children}
            </main>
          </div>
        </QueryClientProvider>
      </body>
    </html>
  );
}
