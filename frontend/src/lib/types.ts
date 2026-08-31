// 与后端 app/schemas.py 对齐的类型。字段与序列化名保持一致（snake_case）。

export interface MeResponse {
  authenticated: boolean;
  username: string | null;
}
