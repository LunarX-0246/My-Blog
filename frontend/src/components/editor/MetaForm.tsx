"use client";

import { useState } from "react";

import { clientFetch } from "@/lib/api";
import type { CategoryOut, PostWrite, TagOut } from "@/lib/types";

/** 文章属性表单：标题 / slug / 摘要 / 分类（单选）/ 标签（多选）/ 精选。 */
interface Props {
  value: PostWrite;
  categories: CategoryOut[];
  tags: TagOut[];
  onChange: (v: PostWrite) => void;
}

const inputCls =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-faint focus:border-accent focus:outline-none";

const labelCls = "text-sm text-muted";

export default function MetaForm({ value, categories, tags, onChange }: Props) {
  // 分类 / 标签可在编辑界面内直接新建（FR-POST-16），新建后追加到本地列表
  const [allCategories, setAllCategories] = useState<CategoryOut[]>(categories);
  const [allTags, setAllTags] = useState<TagOut[]>(tags);
  const [creatingCategory, setCreatingCategory] = useState(false);
  const [newCategory, setNewCategory] = useState("");
  const [creatingTag, setCreatingTag] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleCreateCategory() {
    const name = newCategory.trim();
    if (!name) return;
    setBusy(true);
    try {
      const c = await clientFetch<CategoryOut>("/api/categories", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setAllCategories((prev) => (prev.some((x) => x.id === c.id) ? prev : [...prev, c]));
      onChange({ ...value, category_id: c.id });
      setNewCategory("");
      setCreatingCategory(false);
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateTag() {
    const name = newTag.trim();
    if (!name) return;
    setBusy(true);
    try {
      const t = await clientFetch<TagOut>("/api/tags", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setAllTags((prev) => (prev.some((x) => x.id === t.id) ? prev : [...prev, t]));
      onChange({ ...value, tag_ids: [...value.tag_ids, t.id] });
      setNewTag("");
      setCreatingTag(false);
    } finally {
      setBusy(false);
    }
  }

  function toggleTag(id: number) {
    const has = value.tag_ids.includes(id);
    onChange({
      ...value,
      tag_ids: has ? value.tag_ids.filter((x) => x !== id) : [...value.tag_ids, id],
    });
  }

  return (
    <div className="space-y-4">
      <label className="block space-y-1.5">
        <span className={labelCls}>标题</span>
        <input
          className={inputCls}
          value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
          placeholder="文章标题"
        />
      </label>

      <label className="block space-y-1.5">
        <span className={labelCls}>URL 别名（slug）</span>
        <input
          className={inputCls}
          value={value.slug ?? ""}
          onChange={(e) => onChange({ ...value, slug: e.target.value })}
          placeholder="留空则由标题自动生成"
        />
      </label>

      <label className="block space-y-1.5">
        <span className={labelCls}>摘要</span>
        <textarea
          className={inputCls}
          rows={2}
          value={value.summary}
          onChange={(e) => onChange({ ...value, summary: e.target.value })}
          placeholder="一句话摘要，列表页与来源卡片展示"
        />
      </label>

      {/* 分类：单选 */}
      <div className="space-y-1.5">
        <span className={labelCls}>分类</span>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={`${inputCls} w-auto min-w-[10rem]`}
            value={value.category_id ?? ""}
            onChange={(e) =>
              onChange({ ...value, category_id: e.target.value ? Number(e.target.value) : null })
            }
          >
            <option value="">未分类</option>
            {allCategories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          {creatingCategory ? (
            <span className="flex items-center gap-1">
              <input
                className={`${inputCls} w-40`}
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                placeholder="新分类名"
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && handleCreateCategory()}
              />
              <button type="button" disabled={busy} onClick={handleCreateCategory} className="text-sm text-accent">
                确定
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setCreatingCategory(true)} className="text-sm text-muted hover:text-foreground">
              + 新建分类
            </button>
          )}
        </div>
      </div>

      {/* 标签：多选 */}
      <div className="space-y-1.5">
        <span className={labelCls}>标签</span>
        <div className="flex flex-wrap items-center gap-2">
          {allTags.map((t) => {
            const active = value.tag_ids.includes(t.id);
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => toggleTag(t.id)}
                className={`rounded-full border px-3 py-1 text-sm ${
                  active
                    ? "border-accent bg-accent text-accent-foreground"
                    : "border-border text-muted hover:text-foreground"
                }`}
              >
                {t.name}
              </button>
            );
          })}
          {creatingTag ? (
            <span className="flex items-center gap-1">
              <input
                className={`${inputCls} w-32 py-1`}
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                placeholder="新标签名"
                autoFocus
                onKeyDown={(e) => e.key === "Enter" && handleCreateTag()}
              />
              <button type="button" disabled={busy} onClick={handleCreateTag} className="text-sm text-accent">
                确定
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setCreatingTag(true)} className="text-sm text-muted hover:text-foreground">
              + 新建标签
            </button>
          )}
        </div>
      </div>

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={value.is_featured}
          onChange={(e) => onChange({ ...value, is_featured: e.target.checked })}
        />
        <span className={labelCls}>设为精选（首页「精选文章」展示）</span>
      </label>
    </div>
  );
}
