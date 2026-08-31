/** 关于页（FR-VIEW-23/24）：介绍博主身份、技术方向、能力与联系方式。 */
export default function AboutPage() {
  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-2xl font-semibold">关于</h1>
        <p className="text-muted">
          这里是博主的自我介绍。技术方向、项目经历与联系方式将在此展示。
        </p>
        <section className="space-y-2">
          <h2 className="text-lg font-medium">技术方向</h2>
          <p className="text-muted">后端开发 / RAG 与 Agent 应用 / 系统设计。</p>
        </section>
        <section className="space-y-2">
          <h2 className="text-lg font-medium">联系方式</h2>
          <p className="text-muted">GitHub · 邮箱 · RSS（待补充）。</p>
        </section>
      </div>
    </main>
  );
}
