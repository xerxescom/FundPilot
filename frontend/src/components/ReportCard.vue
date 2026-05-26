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
  let inTable = false;
  let tableHeader: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Close open structures on empty line
    if (!trimmed) {
      if (inList) { html.push("</ul>"); inList = false; }
      if (inTable) { html.push("</tbody></table>"); inTable = false; tableHeader = []; }
      continue;
    }

    // Detect table header followed by separator line
    if (!inTable && trimmed.includes("|")) {
      const next = (lines[i + 1] || "").trim();
      const separator = /^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?$/;
      if (separator.test(next)) {
        inTable = true;
        tableHeader = trimmed.split("|").map(c => c.trim()).filter(c => c.length);
        html.push("<table><thead><tr>");
        tableHeader.forEach(col => html.push(`<th>${renderInline(col)}</th>`));
        html.push("</tr></thead><tbody>");
        i++; // skip separator line
        continue;
      }
    }

    // Inside table rows
    if (inTable) {
      if (trimmed.includes("|")) {
        const cols = trimmed.split("|").map(c => c.trim()).filter(c => c.length);
        html.push("<tr>");
        cols.forEach(col => html.push(`<td>${renderInline(col)}</td>`));
        html.push("</tr>");
        continue;
      } else {
        html.push("</tbody></table>");
        inTable = false;
        tableHeader = [];
        // fall through to normal processing
      }
    }

    // Headings
    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      if (inList) { html.push("</ul>"); inList = false; }
      const level = Math.min(heading[1].length + 1, 5);
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    // List items
    const listItem = /^[-*]\s+(.+)$/.exec(trimmed);
    if (listItem) {
      if (!inList) { html.push("<ul>"); inList = true; }
      html.push(`<li>${renderInline(listItem[1])}</li>`);
      continue;
    }

    if (inList) { html.push("</ul>"); inList = false; }
    html.push(`<p>${renderInline(trimmed)}</p>`);
  }

  if (inList) html.push("</ul>");
  if (inTable) html.push("</tbody></table>");
  return html.join("");
}

const renderedContent = computed(() => renderMarkdown(props.report.content || ""));
</script>
