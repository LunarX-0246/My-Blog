// 标题锚点 slug 与自定义 rehype 插件。
// 与后端 rag/markdown.py 的 slugify_heading 逐字一致，否则引用跳转会错位（FR-VIEW-11）。

import type { Element, Root, Text } from "hast";

/** 与后端一致的锚点 slug 算法：小写 → 去反引号 → 非 [a-z0-9 中文 扩展A] 换 '-' → 去首尾 '-'。 */
export function slugifyHeading(text: string): string {
  let s = text.toLowerCase().replace(/`/g, "");
  s = s.replace(/[^a-z0-9一-鿿㐀-䶿]+/g, "-");
  s = s.replace(/^-+|-+$/g, "");
  return s || "section";
}

/** 从 hast 标题节点提取纯文本（去掉加粗/斜体/链接/内联代码标记）。 */
function extractText(node: Element): string {
  let out = "";
  for (const child of node.children) {
    if (child.type === "text") {
      out += child.value;
    } else if (child.type === "element") {
      if (child.tagName === "img") {
        out += (child.properties?.alt as string) ?? "";
      } else {
        out += extractText(child);
      }
    }
  }
  return out;
}

/**
 * 自定义 rehype 插件：给 h1~h6 加 id，锚点带去重（重复标题加 -1、-2）。
 * rehype-slug v6 只支持 prefix、固定用 github-slugger，无法保证与后端一致，故自写。
 */
export function rehypeHeadingIds() {
  const seen = new Map<string, number>();
  return (tree: Root): void => {
    const walk = (nodes: (Element | Text)[]): void => {
      for (const node of nodes) {
        if (node.type === "element") {
          if (/^h[1-6]$/.test(node.tagName)) {
            const base = slugifyHeading(extractText(node));
            const n = seen.get(base) ?? 0;
            seen.set(base, n + 1);
            node.properties = node.properties ?? {};
            node.properties.id = n === 0 ? base : `${base}-${n}`;
          }
          walk(node.children as (Element | Text)[]);
        }
      }
    };
    walk(tree.children as (Element | Text)[]);
  };
}
