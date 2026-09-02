"use client";

/**
 * PDF 原文视图（FR-VIEW-18、FR-VIEW-22）。
 *
 * 用浏览器内置的 PDF 阅读器（iframe 嵌入），而不是第三方 React 组件。
 *
 * 为什么换掉 @react-pdf-viewer：
 *   1. 该库 3.12 发布于 React 19 之前，在 React 19 下组件只渲染出根节点、
 *      从不初始化文档 —— 页面上一片空白，既不报错也没有 loading 指示，
 *      排查成本极高。
 *   2. 浏览器内置阅读器同样满足 FR-VIEW-18 要求的翻页、缩放、页内查找，
 *      而且是真正意义上的「原生」。
 *   3. 跳页靠 PDF URL 的 `#page=N` 片段 —— 这是 PDF 打开参数的标准写法，
 *      不依赖任何库。
 *   4. 顺带去掉三个依赖（@react-pdf-viewer/core、default-layout、pdfjs-dist）
 *      与 public/pdf.worker.min.js（约 1 MB）。目标服务器只有 1.6 GiB 内存，
 *      前端镜像越小越好。
 *
 * ⚠️ 依赖后端 /api/docs/{id}/raw 返回 `application/pdf` 且**不带 filename** ——
 * 带了会变成 Content-Disposition: attachment，iframe 里什么都不显示。
 */
export default function PdfViewer({ url, initialPage }: { url: string; initialPage?: number }) {
  // #page 是 1 基（PDF 打开参数的约定），后端记录的 page_no 也是 1 基，直接用
  const src = initialPage && initialPage > 1 ? `${url}#page=${initialPage}` : url;
  return (
    <iframe
      // key 让页码变化时强制重建 iframe：只改 URL 的 hash 部分浏览器不会重新导航，
      // 页码不会生效
      key={src}
      src={src}
      title="PDF 原文"
      className="h-[70vh] w-full rounded-lg border border-border bg-surface"
    />
  );
}
