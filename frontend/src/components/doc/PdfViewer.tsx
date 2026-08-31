"use client";

import { Worker, Viewer } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";

/** PDF 原文视图（FR-VIEW-18）。initialPage 为 1 基页码（来自 ?page=N），内部转 0 基。 */
export default function PdfViewer({ url, initialPage }: { url: string; initialPage?: number }) {
  const defaultLayout = defaultLayoutPlugin();
  const pageIndex = initialPage && initialPage > 1 ? initialPage - 1 : 0;
  return (
    <div className="h-[70vh] overflow-hidden rounded-lg border border-border">
      <Worker workerUrl="/pdf.worker.min.js">
        <Viewer fileUrl={url} plugins={[defaultLayout]} initialPage={pageIndex} />
      </Worker>
    </div>
  );
}
