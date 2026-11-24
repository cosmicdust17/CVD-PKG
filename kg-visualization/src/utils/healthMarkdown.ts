import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import type { Source } from './healthApi'

const markdown = new MarkdownIt({ html: false }).disable('image')

export function citationNumber(source: Source, index: number) {
  return source.citation_number ?? index + 1
}

markdown.renderer.rules.text = (tokens, index, _options, env) => {
  const citations = env?.citations
  const text = markdown.utils.escapeHtml(tokens[index].content)
  return text.replace(/\[(\d+)\]/g, (label, number) => citations instanceof Set && citations.has(Number(number))
    ? '<button type="button" class="ai-citation" data-citation="' + number + '" aria-label="查看文献 ' + number + '">' + label + '</button>'
    : label)
}

export function renderHealthMarkdown(value: string, sources: Source[]) {
  const citations = new Set(sources.map(citationNumber))
  return DOMPurify.sanitize(markdown.render(value, { citations }), {
    ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'strong', 'em', 's', 'ul', 'ol', 'li', 'blockquote',
      'br', 'hr', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'button'],
    ALLOWED_ATTR: ['href', 'title', 'class', 'type', 'start', 'aria-label', 'data-citation'],
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
  })
}

export function legacyMarkdown(value: string) {
  const references = new Set<string>()
  const text = value.replace(/(^|\n\n)「[^」]*」\s*\[(\d+)\](?=\s*(?:\n\n|$))/g, (_, _start, number) => {
    references.add('[' + number + ']')
    return ''
  }).replace(/(?:已展示文献摘录。)?相关原文如下。/g, '').trim()
  return [text, references.size ? '查看相关文献 ' + [...references].join(' ') : ''].filter(Boolean).join('\n\n')
}

export function shortSummary(value: string) {
  const tokens = markdown.parse(value, {})
  const paragraph = tokens.find((token, index) => token.type === 'inline' && tokens[index - 1]?.type === 'paragraph_open')
    ?? tokens.find(token => token.type === 'inline')
  const text = (paragraph?.children ?? []).map(token => token.type.endsWith('break') ? ' ' : token.content)
    .join('').replace(/\[\d+\]/g, '').trim().replace(/\s+/g, ' ')
  return text.length > 62 ? text.slice(0, 61) + '…' : text
}

export function displayExcerpt(value: string) {
  return value.replace(/\r\n?/g, '\n').trim().split(/\n[ \t\u3000]*\n+/)
    .map(paragraph => paragraph
      .replace(/([\p{Script=Han}、，。；：！？）】])[ \t\u3000]*\n[ \t\u3000]*(?=[\p{Script=Han}、，。；：！？）】])/gu, '$1')
      .replace(/\s*\n\s*/g, ' ')
      .replace(/[ \t\u3000]+/g, ' ')
      .replace(/ +([、，。；：！？）》】％%,.;:!?)\]])/g, '$1')
      .trim())
    .join('\n\n')
}
