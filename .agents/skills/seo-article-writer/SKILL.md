---
name: seo-article-writer
description: >-
  Use this skill when creating, structuring, reviewing, or optimizing blog articles
  for Google Search indexing and organic ranking (SEO on-page, Helpful Content / E-E-A-T,
  Schema.org JSON-LD, semantic HTML, internal linking, and sitemap updates).
---

# SEO Article Writer (Google Indexing & Ranking Reference)

Use this skill whenever the user asks to write, outline, review, or optimize an article for the blog (`blog/*.html`) or any editorial page aimed at ranking on Google Search and Google Discover.

---

## 1. Search Intent & Keyword Strategy

Before writing a single line of HTML or copy, define:

1. **Primary Keyword (1 per article):** The main query this page targets. Never target the exact same primary keyword as an existing article in `blog/` (avoid keyword cannibalization).
2. **Search Intent:**
   - **Informational** ("como funciona...", "o que é..."): focus on clear definitions, step-by-step guides, and practical examples.
   - **Commercial / Comparative** ("melhor ferramenta...", "manual vs automático"): include comparison tables, pros/cons, and clear criteria.
   - **Checklist / Actionable** ("checklist pós-licitação..."): use numbered steps, scannable lists, and downloadable/copyable structure.
3. **Secondary / Semantic Keywords:** 3–6 related terms and common questions (People Also Ask) to cover naturally across `<h2>`/`<h3>` headings and paragraphs.
4. **URL Slug (`blog/<slug>.html`):**
   - Lowercase, hyphen-separated, ASCII only (no accents or `ç`).
   - Include the primary keyword, remove unnecessary stop words (`de`, `para`, `o`, `a`), keep it under 60 characters, and avoid dates/years in the slug so the URL stays evergreen.

---

## 2. Content Structure Google Loves (Helpful Content + E-E-A-T)

Google's ranking systems reward **people-first content** with strong **E-E-A-T** (Experience, Expertise, Authoritativeness, Trustworthiness):

- **Direct Answer Upfront (Inverted Pyramid):** Answer the core question clearly within the first 1–2 paragraphs (40–60 words). This improves user retention and eligibility for **Featured Snippets** and **AI Overviews**.
- **Strict Heading Hierarchy:**
  - Exactly **one `<h1>`** per page, matching the search intent and aligned with `<title>`.
  - Use `<h2>` for major sections (often phrased as clear questions or action topics) and `<h3>` for subpoints. Never skip heading levels (`h1` -> `h3`).
- **Scannability:**
  - Keep paragraphs short (2–4 lines, ~40–70 words).
  - Use `<ul>` / `<ol>` lists, comparison `<table>`s, and `<strong>` highlights for key takeaways—never walls of text.
- **Depth & Original Value (No Fluff / No Thin Content):**
  - Include concrete examples, legal/operational context (e.g., deadlines, real scenarios, official sources), and actionable next steps.
  - Cite official sources where relevant (e.g., Lei 14.133/2021, Diário Oficial da União, Portal Nacional de Contratações Públicas) instead of vague claims.
- **Visible Freshness & Authorship:**
  - Display publication date (and update date when revised), estimated reading time, and category in `.meta-line`.

---

## 3. Technical On-Page SEO & Metadata

Every article in `blog/` MUST include complete, consistent metadata in `<head>`:

- **`<title>` (50–60 chars):** Primary keyword near the start + brand suffix (`| Sentinela Diário`). Avoid truncation and clickbait.
- **`<meta name="description">` (140–160 chars):** Summarize the exact value of the article with a natural keyword mention and clear reason to click.
- **`<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1" />`:** Ensures full indexing and eligibility for large image previews in Google Discover.
- **`<link rel="canonical" href="https://sentineladiario.com/blog/<slug>.html" />`:** Absolute HTTPS URL matching the exact filename.
- **Open Graph & Twitter Cards:** `og:type="article"`, `og:locale="pt_BR"`, `og:title`, `og:description`, `og:url`, `og:image`, `article:published_time`, `article:modified_time`, `article:section`, `twitter:card="summary_large_image"`.

For detailed specifications and edge cases, read [Google Indexing Checklist](./references/google-indexing-checklist.md).

---

## 4. Structured Data (Schema.org JSON-LD)

Include valid JSON-LD blocks inside `<head>`:

1. **`Article` (or `BlogPosting`):**
   - Required/recommended fields: `headline` (<= 110 chars), `description`, `image` (absolute URL, >= 1200px wide), `datePublished` (`YYYY-MM-DD` or ISO-8601), `dateModified`, `author`, `publisher`, `mainEntityOfPage`.
2. **`BreadcrumbList`:**
   - Reflects the visible breadcrumb navigation (`Início` -> `Blog` -> `Article short title`).
3. **`FAQPage` (Conditional):**
   - Add **only** if the article contains a visible, dedicated FAQ section in the HTML body with the exact same questions and answers. Never include hidden FAQ schema.

See copy-pasteable templates in [Google Indexing Checklist](./references/google-indexing-checklist.md).

---

## 5. Images, Accessibility & Core Web Vitals

- **Hero Image (LCP):** Place inside `<figure class="hero-img">` with `loading="eager"`, `fetchpriority="high"`, and explicit `width` and `height` attributes (prevents CLS).
- **Secondary Images:** Use `loading="lazy"` and explicit `width` and `height`.
- **Format & Size:** Prefer `.webp` or optimized `.jpg` (`>= 1200x675` / 16:9 for hero images to qualify for Google Discover, compressed under ~150 KB).
- **Descriptive `alt` Text & Filename:** Name files descriptively (`blog/img/<slug>.jpg`) and write `alt` text describing the image naturally without keyword stuffing.

---

## 6. Internal Linking & Publishing Workflow (`sentinela-diario`)

When creating or publishing an article in this repository:

1. **Draft from Template:** Start from [article-template.html](./examples/article-template.html) so layout, CSS tokens, header/footer, GA4 snippet, and SEO tags match existing posts in `blog/`.
2. **Contextual Internal Links:**
   - Add 2–4 natural inline links or a `.related` section pointing to relevant existing articles in `blog/` (check `sitemap.xml` for current URLs).
   - Link naturally to the main conversion page (`/#teste-gratis` or `/`) inside `.callout` and `.cta-box`.
3. **Update `blog/index.html`:** Add a new `.post-card` entry for the article so crawlers and readers discover it from the blog hub.
4. **Update `sitemap.xml`:** Add the new `<url>` entry with `<loc>`, `<lastmod>` (`YYYY-MM-DD`), `<changefreq>monthly</changefreq>`, and `<priority>0.8</priority>`.
5. **Check `robots.txt`:** Confirm `/blog/` is crawlable and `Sitemap:` points to `https://sentineladiario.com/sitemap.xml`.

---

## 7. Pre-Publish Validation Checklist

Before finalizing the article, verify:

- [ ] Only 1 `<h1>` exists; headings follow `h1 -> h2 -> h3` without skips.
- [ ] `<title>` is ~50–60 chars and `<meta name="description">` is ~140–160 chars.
- [ ] `<link rel="canonical">`, `og:url`, and `mainEntityOfPage.@id` match the exact `https://sentineladiario.com/blog/<slug>.html` URL.
- [ ] JSON-LD (`Article` + `BreadcrumbList`, plus `FAQPage` if visible FAQ exists) is valid JSON with no trailing commas.
- [ ] All images have `width`, `height`, and descriptive `alt` text; hero image uses `loading="eager"`.
- [ ] Internal links to existing `blog/*.html` pages resolve to real files in `blog/`.
- [ ] `blog/index.html` and `sitemap.xml` have been updated with the new article.
