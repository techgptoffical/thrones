import { Check, Copy } from "lucide-react";
import { memo, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { copyText } from "../lib/format";
import type { Source } from "../types";

/** Apply `fn` to prose only, leaving fenced and inline code untouched. */
function outsideCode(text: string, fn: (s: string) => string): string {
  return text
    .split(/(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g)
    .map((part, i) => (i % 2 ? part : fn(part)))
    .join("");
}

function prepare(text: string, sourceCount: number): string {
  return outsideCode(text, (s) => {
    // Models often write \( \) and \[ \]; remark-math expects dollar delimiters.
    let out = s
      .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `\n$$\n${m.trim()}\n$$\n`)
      .replace(/\\\((.+?)\\\)/g, (_, m) => `$${m.trim()}$`);
    if (sourceCount > 0) {
      out = out.replace(/\[(\d{1,2})\](?!\()/g, (whole, n) =>
        Number(n) >= 1 && Number(n) <= sourceCount ? `[${n}](#cite-${n})` : whole,
      );
    }
    return out;
  });
}

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node) {
    return textOf((node as { props: { children?: ReactNode } }).props.children);
  }
  return "";
}

function CodeBlock({ lang, children }: { lang: string; children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    if (await copyText(textOf(children).replace(/\n$/, ""))) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  };
  return (
    <div className="codeblock">
      <div className="bar">
        <span>{lang || "text"}</span>
        <button className="copy" onClick={copy} aria-label="Copy code">
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function Citation({ n, source }: { n: number; source?: Source }) {
  if (!source) return <>[{n}]</>;
  return (
    <span className="cite">
      <a href={source.url} target="_blank" rel="noreferrer noopener" aria-label={`Source ${n}: ${source.title}`}>
        {n}
      </a>
      <span className="card" role="tooltip">
        <span className="site">
          {source.site}
          {source.date ? ` · ${source.date}` : ""}
        </span>
        <span className="ttl">{source.title}</span>
        {source.snippet && <span className="snip">{source.snippet}</span>}
      </span>
    </span>
  );
}

interface Props {
  text: string;
  sources?: Source[];
}

export const Markdown = memo(function Markdown({ text, sources }: Props) {
  const web = useMemo(() => (sources ?? []).filter((s) => s.kind === "web"), [sources]);
  const prepared = useMemo(() => prepare(text, web.length), [text, web.length]);

  const components = useMemo<Components>(
    () => ({
      pre({ children }) {
        const child = Array.isArray(children) ? children[0] : children;
        const cls: string = (child as { props?: { className?: string } })?.props?.className ?? "";
        const lang = /language-([\w+-]+)/.exec(cls)?.[1] ?? "";
        return <CodeBlock lang={lang}>{children}</CodeBlock>;
      },
      table({ children }) {
        return (
          <div className="table-wrap">
            <table>{children}</table>
          </div>
        );
      },
      a({ href, children }) {
        if (href?.startsWith("#cite-")) {
          const n = Number(href.slice(6));
          return <Citation n={n} source={web.find((s) => s.n === n)} />;
        }
        return (
          <a href={href} target="_blank" rel="noreferrer noopener">
            {children}
          </a>
        );
      },
      // Remote images would be an undisclosed network request; show the link instead.
      img({ src, alt }) {
        return (
          <a href={typeof src === "string" ? src : undefined} target="_blank" rel="noreferrer noopener">
            {alt || "image"}
          </a>
        );
      },
    }),
    [web],
  );

  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }], [rehypeHighlight, { detect: false }]]}
        components={components}
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );
});
