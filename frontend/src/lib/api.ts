// FastAPI 调用封装（客户端侧）。
// 客户端请求走同源 /api（经 next.config.ts 的 rewrite 代理到后端），浏览器自动带 Cookie。

export interface ApiErrorShape {
  error: { code: string; message: string };
}

/** 后端统一错误。message 是面向用户的中文，code 是机器可读标识。 */
export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

/** 解析后端响应；非 2xx 抛 ApiError。 */
export async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiErrorShape | null;
    throw new ApiError(
      res.status,
      body?.error?.code ?? "error",
      body?.error?.message ?? `请求失败（${res.status}）`,
    );
  }
  return (await res.json()) as T;
}

/** 客户端取数：同源 /api，经 Next.js rewrite 代理到后端，浏览器自动带 Cookie。 */
export async function clientFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  return parseResponse<T>(res);
}
