/**
 * Client-side internationalization.
 *
 * The server renders the active catalog into window.__CF_I18N__ so browser code
 * and Jinja templates share one set of translations. Call the exported helper
 * with the English source text; it returns the translation for the active
 * locale and falls back to the source text when no entry exists.
 *
 * Placeholders use {name} syntax:
 *   _('Deleted {count} tools', { count: 3 })
 */

const globalScope = typeof window !== 'undefined' ? window : globalThis;

function readInjected() {
  const injected = globalScope.__CF_I18N__;
  if (injected && typeof injected === 'object') {
    return {
      locale: typeof injected.locale === 'string' ? injected.locale : 'en',
      messages: injected.messages && typeof injected.messages === 'object' ? injected.messages : {},
    };
  }
  return { locale: 'en', messages: {} };
}

let activeLocale = readInjected().locale;
let dictionary = readInjected().messages;

/**
 * Return the locale the page was rendered with.
 * @returns {string} Locale code such as 'en' or 'zh-CN'.
 */
export function currentLocale() {
  return activeLocale;
}

/**
 * Replace every catalog entry. Used when a page refreshes its dictionary
 * without a full reload.
 * @param {Object<string, string>} messages - Source to translated message map.
 * @param {string} [locale] - Locale the messages belong to.
 */
export function setDictionary(messages, locale) {
  dictionary = messages && typeof messages === 'object' ? messages : {};
  if (typeof locale === 'string') {
    activeLocale = locale;
  }
  globalScope.__CF_I18N__ = { locale: activeLocale, messages: dictionary };
}

/**
 * Translate a message into the active locale.
 * @param {string} message - Source message, written in English.
 * @param {Object<string, (string|number)>} [variables] - Values for {name} placeholders.
 * @returns {string} The translated message.
 */
export function translate(message, variables) {
  if (typeof message !== 'string') {
    return message;
  }
  const template = Object.prototype.hasOwnProperty.call(dictionary, message) ? dictionary[message] : message;
  if (!variables) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, name) => (
    Object.prototype.hasOwnProperty.call(variables, name) ? String(variables[name]) : match
  ));
}

/**
 * Alias used across the Admin UI, matching the Python and Jinja convention.
 * @param {string} message - Source message, written in English.
 * @param {Object<string, (string|number)>} [variables] - Values for {name} placeholders.
 * @returns {string} The translated message.
 */
export function _(message, variables) {
  return translate(message, variables);
}

// Expose the helper so inline handlers and non-module scripts can translate
// without importing this module.
globalScope._ = _;
globalScope.cfI18n = { _ , translate, currentLocale, setDictionary };
