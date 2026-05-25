import axios from "axios";
import { ElMessage } from "element-plus";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  timeout: 120000,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join("；")
      : detail || error.message || "请求失败";
    ElMessage.error(message);
    return Promise.reject(error);
  },
);

export async function getJson<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const response = await apiClient.get<T>(url, { params });
  return response.data;
}

export async function postJson<T>(url: string, data?: unknown): Promise<T> {
  const response = await apiClient.post<T>(url, data);
  return response.data;
}

export async function putJson<T>(url: string, data?: unknown): Promise<T> {
  const response = await apiClient.put<T>(url, data);
  return response.data;
}

export async function patchJson<T>(url: string, data?: unknown): Promise<T> {
  const response = await apiClient.patch<T>(url, data);
  return response.data;
}

export async function deleteJson<T>(url: string): Promise<T> {
  const response = await apiClient.delete<T>(url);
  return response.data;
}
