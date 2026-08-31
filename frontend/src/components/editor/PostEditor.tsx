"use client";

import { useEffect, useState } from "react";
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

/** 文章编辑器：属性表单 + 正文。postId 为 null 表示新建。 */
export default function PostEditor({ postId }: { postId: number | null }) {
  const router = useRouter();
  const [form, setForm] = useState<PostWrite>(emptyForm);
  const [categories, setCategories] = useState<CategoryOut[]>([]);
  const [tags, setTags] = useState<TagOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  function buildBody(): PostWrite {
    return { ...form, slug: form.slug?.trim() || null };
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      if (postId == null) {
        const p = await clientFetch<PostDetail>("/api/posts", {
          method: "POST",
          body: JSON.stringify(buildBody()),
        });
        router.replace(`/admin/posts/${p.id}/edit`);
      } else {
        await clientFetch<PostDetail>(`/api/posts/${postId}`, {
          method: "PUT",
          body: JSON.stringify(buildBody()),
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function publish() {
    setSaving(true);
    setError(null);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) {
    return <div className="p-8 text-muted">加载中…</div>;
  }

  const btnBase =
    "rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50";

  return (
    <main className="min-h-screen p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">{postId == null ? "新建文章" : "编辑文章"}</h1>
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
        </header>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <MetaForm value={form} categories={categories} tags={tags} onChange={setForm} />

        <div className="space-y-1.5">
          <span className="text-sm text-muted">正文（Markdown）</span>
          <MarkdownEditor
            value={form.content_md}
            onChange={(v) => setForm({ ...form, content_md: v })}
          />
        </div>
      </div>
    </main>
  );
}
