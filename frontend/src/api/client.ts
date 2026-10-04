import axios from "axios";
import { ElMessage } from "element-plus";

export interface RequestOptions {
  /** 由页面自行展示错误态时置 true，避免全局 toast 与内联错误重复提示 */
  skipErrorToast?: boolean;
}

declare module "axios" {
  export interface AxiosRequestConfig {
    skipErrorToast?: boolean;
  }
}

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 120000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.config?.skipErrorToast) {
      ElMessage.error(errorMessage(error));
    }
    return Promise.reject(error);
  },
);

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join("；");
    if (typeof detail === "string" && detail) return detail;
    return error.message || "请求失败";
  }
  return error instanceof Error ? error.message : "请求失败";
}

export function isNotFound(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404;
}

export async function getJson<T>(
  url: string,
  params?: Record<string, unknown>,
  options?: RequestOptions,
): Promise<T> {
  const response = await apiClient.get<T>(url, { params, ...options });
  return response.data;
}

export async function postJson<T>(
  url: string,
  data?: unknown,
  params?: Record<string, unknown>,
  options?: RequestOptions,
): Promise<T> {
  const response = await apiClient.post<T>(url, data, { params, ...options });
  return response.data;
}

export async function putJson<T>(url: string, data?: unknown, options?: RequestOptions): Promise<T> {
  const response = await apiClient.put<T>(url, data, options);
  return response.data;
}

export async function patchJson<T>(url: string, data?: unknown, options?: RequestOptions): Promise<T> {
  const response = await apiClient.patch<T>(url, data, options);
  return response.data;
}

export async function deleteJson<T>(url: string): Promise<T> {
  const response = await apiClient.delete<T>(url);
  return response.data;
}
