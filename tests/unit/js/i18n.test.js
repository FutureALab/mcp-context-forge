/**
 * Unit tests for the client-side i18n helper (mcpgateway/admin_ui/i18n.js).
 *
 * The module reads window.__CF_I18N__ at import time, so each test resets the
 * module registry and injects the dictionary it needs.
 */

import { describe, test, expect, vi } from "vitest";

/**
 * Import a fresh copy of the module with a given injected dictionary.
 * @param {Object|undefined} injected - Value for window.__CF_I18N__.
 * @returns {Promise<Object>} The freshly imported module.
 */
async function loadI18n(injected) {
  vi.resetModules();
  if (injected === undefined) {
    delete window.__CF_I18N__;
  } else {
    window.__CF_I18N__ = injected;
  }
  return import("../../../mcpgateway/admin_ui/i18n.js");
}

describe("i18n client helper", () => {
  test("translates a catalogued message", async () => {
    const { _ } = await loadI18n({ locale: "zh-CN", messages: { Tools: "工具" } });
    expect(_("Tools")).toBe("工具");
  });

  test("falls back to the source message when no entry exists", async () => {
    const { _ } = await loadI18n({ locale: "zh-CN", messages: { Tools: "工具" } });
    expect(_("Not In Catalog")).toBe("Not In Catalog");
  });

  test("interpolates named placeholders", async () => {
    const { _ } = await loadI18n({ locale: "zh-CN", messages: { "Deleted {count} tools": "已删除 {count} 个工具" } });
    expect(_("Deleted {count} tools", { count: 3 })).toBe("已删除 3 个工具");
  });

  test("keeps placeholders that have no value", async () => {
    const { _ } = await loadI18n({ locale: "en", messages: { "Hello {name}": "Hello {name}" } });
    expect(_("Hello {name}", {})).toBe("Hello {name}");
  });

  test("reports the injected locale", async () => {
    const { currentLocale } = await loadI18n({ locale: "zh-CN", messages: {} });
    expect(currentLocale()).toBe("zh-CN");
  });

  test("defaults to English with no injected dictionary", async () => {
    const { _, currentLocale } = await loadI18n(undefined);
    expect(currentLocale()).toBe("en");
    expect(_("Tools")).toBe("Tools");
  });

  test("ignores a malformed injected payload", async () => {
    const { _, currentLocale } = await loadI18n({ locale: 42, messages: "nope" });
    expect(currentLocale()).toBe("en");
    expect(_("Tools")).toBe("Tools");
  });

  test("setDictionary replaces the catalog at runtime", async () => {
    const { _, setDictionary, currentLocale } = await loadI18n({ locale: "en", messages: {} });
    expect(_("Tools")).toBe("Tools");
    setDictionary({ Tools: "工具" }, "zh-CN");
    expect(_("Tools")).toBe("工具");
    expect(currentLocale()).toBe("zh-CN");
    expect(window.__CF_I18N__.messages.Tools).toBe("工具");
  });

  test("exposes the helper on window for inline scripts", async () => {
    const { _ } = await loadI18n({ locale: "zh-CN", messages: { Search: "搜索" } });
    expect(typeof window._).toBe("function");
    expect(window._("Search")).toBe("搜索");
    expect(window.cfI18n._("Search")).toBe("搜索");
    expect(window.cfI18n._).toBe(_);
  });

  test("returns non-string input unchanged", async () => {
    const { translate } = await loadI18n({ locale: "en", messages: {} });
    expect(translate(undefined)).toBeUndefined();
  });
});
