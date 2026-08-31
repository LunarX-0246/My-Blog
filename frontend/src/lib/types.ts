// 与后端 app/schemas.py 对齐的类型。字段与序列化名保持一致（snake_case）。

export interface MeResponse {
  authenticated: boolean;
  username: string | null;
}

export interface CategoryOut {
  id: number;
  name: string;
  slug: string;
}

export interface TagOut {
  id: number;
  name: string;
  slug: string;
}

export interface TocItem {
  level: number;
  text: string;
  anchor: string;
}

export type PostStatus = "draft" | "published";

export interface PostListItem {
  id: number;
  title: string;
  slug: string;
  summary: string;
  status: PostStatus;
  is_featured: boolean;
  read_minutes: number;
  view_count: number;
  idx_status: string;
  idx_error: string | null;
  category: CategoryOut | null;
  tags: TagOut[];
  published_at: string | null;
  updated_at: string;
  created_at: string;
}

export interface PostDetail extends PostListItem {
  content_md: string;
  category_id: number | null;
  tag_ids: number[];
  toc: TocItem[];
}

export interface PostWrite {
  title: string;
  slug: string | null;
  summary: string;
  content_md: string;
  category_id: number | null;
  tag_ids: number[];
  is_featured: boolean;
}

export interface PostListResponse {
  items: PostListItem[];
  total: number;
}

export interface PostNeighbor {
  title: string;
  slug: string;
}

export interface NeighborsResponse {
  prev: PostNeighbor | null;
  next: PostNeighbor | null;
}
