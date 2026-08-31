"use client";

import { Worker, Viewer } from "@react-pdf-viewer/core";
import { defaultLayoutPlugin } from "@react-pdf-viewer/default-layout";
import "@react-pdf-viewer/core/lib/styles/index.css";
import "@react-pdf-viewer/default-layout/lib/styles/index.css";

/** PDF 原文视图（FR-VIEW-18）：原生 PDF 阅读器，支持翻页/缩放/页内查找。 */
export default function PdfViewer({ url }: { url: string }) {
  const defaultLayout = defaultLayoutPlugin();
  return (
    <div className="h-[70vh] overflow-hidden rounded-lg border border-border">
      <Worker workerUrl="/pdf.worker.min.js">
        <Viewer fileUrl={url} plugins={[defaultLayout]} />
      </Worker>
    </div>
  );
}
