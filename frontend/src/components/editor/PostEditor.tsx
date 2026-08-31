"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { clientFetch } from "@/lib/api";
import type { CategoryOut, PostDetail, PostWrite, TagOut } from "@/lib/types";
import MarkdownEditor from "./MarkdownEditor";
import MetaForm from "./MetaForm";

const emptyForm: PostWrite = {
  title: "",
  slug: null,
  summary: "",
  content_md: "",
  category_id: null,
  tag_ids: [],
  is_featured: false,
};

/** 文章编辑器：属性表单 + 正文 + 自动保存。postId 为 null 表示新建。 */
export default function PostEditor({ postId }: { postId: number | null }) {
  const router = useRouter();
  const [form, setForm] = useState<PostWrite>(emptyForm);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [tags, setTags] = useState<TagOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [lastSaved, setLastSaved] = useState<string | null>(null);
  // dirtyRef 供 beforeunload 使用（事件回调里读最新值，避免闭包过期）
  const dirtyRef = useRef(false);

  useEffect(() => {
    async function load() {
      try {
        const [cats, tgs] = await Promise.all([
          clientFetch<CategoryOut[]>("/api/categories"),
          clientFetch<TagOut[]>("/api/tags"),
        ]);
        setCategories(cats);
        setTags(tgs);
        if (postId != null) {
          const p = await clientFetch<PostDetail>(`/api/admin/posts/${postId}`);
          setForm({
            title: p.title,
            slug: p.slug,
            summary: p.summary,
            content_md: p.content_md,
            category_id: p.category_id,
            tag_ids: p.tag_ids,
            is_featured: p.is_featured,
          });
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        setLoaded(true);
      }
    }
    void load();
  }, [postId]);

  function updateForm(v: PostWrite) {
    setForm(v);
    setDirty(true);
    dirtyRef.current = true;
  }

  function buildBody(): PostWrite {
    return { ...form, slug: form.slug?.trim() || null };
  }

  async function persist(silent: boolean) {
    if (postId == null) return;
    if (!silent) setSaving(true);
    try {
      await clientFetch<PostDetail>(`/api/posts/${postId}`, {
        method: "PUT",
        body: JSON.stringify(buildBody()),
      });
      setDirty(false);
      dirtyRef.current = false;
      setLastSaved(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      if (!silent) setSaving(false);
    }
  }

  async function save() {
    setError(null);
    if (postId == null) {
      setSaving(true);
      try {
        const p = await clientFetch<PostDetail>("/api/posts", {
          method: "POST",
          body: JSON.stringify(buildBody()),
        });
        setDirty(false);
        dirtyRef.current = false;
        router.replace(`/admin/posts/${p.id}/edit`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "保存失败");
      } finally {
        setSaving(false);
      }
    } else {
      await persist(false);
    }
  }

  async function generateSummary(): Promise<string | null> {
    setError(null);
    try {
      if (postId == null) {
        // 新建文章先保存为草稿，跳转到编辑页后再点一次即可生成
        const p = await clientFetch<PostDetail>("/api/posts", {
          method: "POST",
          body: JSON.stringify(buildBody()),
        });
        router.replace(`/admin/posts/${p.id}/edit`);
        return null;
      }
      // 先保存最新正文，保证摘要基于当前内容
      await clientFetch<PostDetail>(`/api/posts/${postId}`, {
        method: "PUT",
        body: JSON.stringify(buildBody()),
      });
      const r = await clientFetch<{ summary: string }>(`/api/posts/${postId}/summary`, {
        method: "POST",
      });
      return r.summary;
    } catch (e) {
      setError(e instanceof Error ? e.message : "摘要生成失败");
      return null;
    }
  }

  async function publish() {
    setError(null);
    setSaving(true);
    try {
      let id = postId;
      if (id == null) {
        const p = await clientFetch<PostDetail>("/api/posts", {
          method: "POST",
          body: JSON.stringify(buildBody()),
        });
        id = p.id;
        router.replace(`/admin/posts/${id}/edit`);
      }
      await clientFetch<PostDetail>(`/api/posts/${id}/publish`, { method: "POST" });
      setDirty(false);
      dirtyRef.current = false;
    } catch (e) {
      setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setSaving(false);
    }
  }

  // 自动保存：停止输入 3 秒后静默保存草稿（FR-POST-06）
  useEffect(() => {
    if (!loaded || postId == null || !dirty) return;
    const t = setTimeout(() => void persist(true), 3000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, form, postId, loaded]);

  // 离开页面时若有未保存修改，给出确认提示（FR-POST-07）
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

  if (!loaded) {
    return <div className="p-8 text-muted">加载中…</div>;
  }

  const btnBase = "rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50";

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">{postId == null ? "新建文章" : "编辑文章"}</h1>
          <div className="flex items-center gap-3">
            {lastSaved && <span className="text-xs text-faint">已保存 {lastSaved}</span>}
            <div className="flex gap-2">
              <button
                onClick={save}
                disabled={saving}
                className={`${btnBase} border border-border text-muted hover:text-foreground`}
              >
                {saving ? "保存中…" : "保存"}
              </button>
              <button
                onClick={publish}
                disabled={saving}
                className={`${btnBase} bg-accent text-accent-foreground hover:opacity-90`}
              >
                发布
              </button>
            </div>
          </div>
        </header>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <MetaForm
          value={form}
          categories={categories}
          tags={tags}
          onChange={updateForm}
          onGenerateSummary={generateSummary}
        />

        <div className="space-y-1.5">
          <span className="text-sm text-muted">正文（Markdown）</span>
          <MarkdownEditor
            value={form.content_md}
            onChange={(v) => updateForm({ ...form, content_md: v })}
          />
        </div>
      </div>
    </main>
  );
}
