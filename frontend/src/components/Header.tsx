import Link from "next/link";

const navItems = [
  { href: "/", label: "首页" },
  { href: "/posts", label: "文章" },
  { href: "/docs", label: "知识库" },
  { href: "/ai", label: "AI 问答" },
  { href: "/about", label: "关于" },
];

/** 全局导航（FR-VIEW-04）。 */
export default function Header() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-2 px-6 py-4">
        <Link href="/" className="font-semibold">
          My Blog
        </Link>
        <nav className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          {navItems.map((i) => (
            <Link key={i.href} href={i.href} className="hover:text-foreground">
              {i.label}
            </Link>
          ))}
          <form action="/search" className="ml-1">
            <input
              name="q"
              type="search"
              placeholder="搜索"
              className="w-28 rounded-md border border-border bg-surface px-2 py-1 text-sm text-foreground placeholder:text-faint focus:border-accent focus:outline-none sm:w-36"
            />
          </form>
        </nav>
      </div>
    </header>
  );
}
