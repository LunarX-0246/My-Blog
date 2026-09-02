import type { TocItem } from "@/lib/types";

/**
 * 正文开头的一级标题若与页面标题重复，就把它从渲染内容里去掉。
 *
 * 为什么会重复：Markdown 文件通常把标题写成开头的 `# xxx`，
 * 导入脚本正是从这个 h1 取的标题，上传文档时博主填的标题往往也照抄它。
 * 页头已经用大字号显示过一次标题，正文再渲染一次就成了「标题连着标题」。
 *
 * 只处理**开头第一个**非空行，且文字必须与标题完全一致 ——
 * 正文中间出现的 h1 是作者有意为之，不能动。
 */
export function stripLeadingTitle(md: string, title: string): string {
  const lines = md.split("\n");
  let i = 0;
  while (i < lines.length && lines[i].trim() === "") i += 1;
  const m = lines[i]?.match(/^#\s+(.*)$/);
  if (!m || m[1].trim() !== title.trim()) return md;
  return lines
    .slice(i + 1)
    .join("\n")
    .replace(/^\n+/, "");
}

/**
 * 目录里同步去掉那条重复的一级标题。
 *
 * ★ 必须和 stripLeadingTitle 成对使用：正文里的 h1 被摘掉后，
 *   目录上那一条就指向一个不存在的锚点 —— 点了没反应，
 *   而且滚动高亮逻辑拿它 getElementById 会得到 null。
 */
export function stripLeadingTitleToc(toc: TocItem[], title: string): TocItem[] {
  const first = toc[0];
  if (first && first.level === 1 && first.text.trim() === title.trim()) {
    return toc.slice(1);
  }
  return toc;
}
