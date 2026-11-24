# Google Indexing & Ranking Reference Checklist

Reference details for writing, structuring, and validating articles so Googlebot can crawl, index, understand, and rank them effectively.

---

## 1. JSON-LD Templates

### Article + BreadcrumbList (Required)

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "Título claro e fiel ao H1 (máximo 110 caracteres)",
  "description": "Resumo objetivo do artigo alinhado à meta description.",
  "image": "https://sentineladiario.com/blog/img/slug-do-artigo.jpg",
  "datePublished": "2026-11-23T09:00:00-03:00",
  "dateModified": "2026-11-23T09:00:00-03:00",
  "inLanguage": "pt-BR",
  "author": {
    "@type": "Organization",
    "name": "Sentinela Diário",
    "url": "https://sentineladiario.com/"
  },
  "publisher": {
    "@type": "Organization",
    "name": "Sentinela Diário",
    "url": "https://sentineladiario.com/",
    "logo": {
      "@type": "ImageObject",
      "url": "https://sentineladiario.com/img/logo-512.png",
      "width": 512,
      "height": 512
    }
  },
  "mainEntityOfPage": {
    "@type": "WebPage",
    "@id": "https://sentineladiario.com/blog/slug-do-artigo.html"
  }
}
</script>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    { "@type": "ListItem", "position": 1, "name": "Início", "item": "https://sentineladiario.com/" },
    { "@type": "ListItem", "position": 2, "name": "Blog", "item": "https://sentineladiario.com/blog/" },
    { "@type": "ListItem", "position": 3, "name": "Título curto no breadcrumb" }
  ]
}
</script>
```

### FAQPage (Use ONLY when a visible FAQ section exists in HTML)

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Pergunta exata exibida na página?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Resposta objetiva e idêntica ao conteúdo visível no HTML."
      }
    }
  ]
}
</script>
```

---

## 2. Google Search Essentials & Helpful Content Rules

1. **Originality & Practical Depth:**
   - Do not rewrite generic definitions everyone already knows. Add concrete workflows, edge cases, legal deadlines, or real-world checklists.
2. **Search Intent Match:**
   - Check what type of page ranks for the query (how-to guide, checklist, glossary, comparison) and match that format while delivering clearer structure and better examples.
3. **Avoid Spam & Over-Optimization Signals:**
   - Never stuff keywords unnaturally into headings, alt text, or paragraphs.
   - Never hide text or include JSON-LD content that does not exist visibly on the page.
   - Never create near-duplicate pages targeting minor keyword variations (merge into one authoritative guide instead).
4. **Google Discover Eligibility:**
   - Include `max-image-preview:large` in `<meta name="robots">`.
   - Use a compelling, high-resolution 16:9 image (`>= 1200px` wide) without overlaid promotional banners or excessive text.
   - Write an accurate, curiosity-engaging headline without sensationalist clickbait.

---

## 3. On-Page Copywriting Formula for Articles

1. **Hook + Direct Answer (Intro):**
   - Paragraph 1: State the problem and who it affects.
   - Paragraph 2: Give the direct answer or core takeaway immediately.
2. **Logical Body Sections (`<h2>`):**
   - Use 3 to 6 main `<h2>` sections.
   - Phrase at least 1–2 `<h2>` headings as natural questions users search (helps capture Featured Snippets / People Also Ask).
   - Follow each `<h2>` with a concise 1–2 sentence direct explanation before diving into bullet points or nuances.
3. **Visual Breaks:**
   - Every ~250–350 words, break up prose with a bullet list, numbered checklist, table, or `.callout` box.
4. **FAQ Section (Optional but High Value):**
   - Add 3–4 real user questions near the end of the article (`<h2>Perguntas frequentes</h2>` with `<h3>` per question) and pair with `FAQPage` JSON-LD.
5. **Contextual Next Steps:**
   - End with a clear CTA (`.cta-box`) and 2–3 related articles (`.related`) to reduce bounce rate and strengthen internal PageRank flow.

---

## 4. Post-Publish Indexing Steps (Google Search Console)

After deploying the new HTML file and updated `sitemap.xml`:

1. Open **Google Search Console** -> **Inspeção de URL** (`URL Inspection`).
2. Inspect `https://sentineladiario.com/blog/<slug>.html`.
3. Click **Testar URL publicada** (`Test Live URL`) to confirm status `200`, mobile usability, and detected structured data (`Article`, `BreadcrumbList`).
4. Click **Solicitar indexação** (`Request Indexing`) for faster initial crawling.
5. Verify the updated `sitemap.xml` shows zero errors under **Sitemaps**.
