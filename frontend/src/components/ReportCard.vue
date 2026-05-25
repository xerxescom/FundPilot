<template>
  <div class="panel">
    <div class="toolbar">
      <el-tag>{{ report.model_name || "未知模型" }}</el-tag>
      <el-tag :type="report.is_fallback ? 'warning' : 'success'">
        {{ report.is_fallback ? "规则兜底" : "模型生成" }}
      </el-tag>
      <span class="muted">{{ report.created_at }}</span>
    </div>
    <el-alert v-if="report.fallback_reason" type="warning" :closable="false" :title="report.fallback_reason" />
    <div class="report-content markdown-body" v-html="renderedContent" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { Report } from "../api/types";

const props = defineProps<{ report: Report }>();

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderInline(value: string): string {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(markdown: string): string {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let inList = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
      const level = Math.min(heading[1].length + 1, 5);
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    const listItem = /^[-*]\s+(.+)$/.exec(trimmed);
    if (listItem) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${renderInline(listItem[1])}</li>`);
      continue;
    }

    if (inList) {
      html.push("</ul>");
      inList = false;
    }
    html.push(`<p>${renderInline(trimmed)}</p>`);
  }

  if (inList) html.push("</ul>");
  return html.join("");
}

const renderedContent = computed(() => renderMarkdown(props.report.content || ""));
</script>
