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
      <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
        <Link href="/" className="font-semibold">
          My Blog
        </Link>
        <nav className="flex gap-5 text-sm text-muted">
          {navItems.map((i) => (
            <Link key={i.href} href={i.href} className="hover:text-foreground">
              {i.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
