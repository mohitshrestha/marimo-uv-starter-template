<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:template match="/">
    <html>
      <head>
        <title>RSS Feed | Mohit Shrestha</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&amp;display=swap" rel="stylesheet"/>
      </head>
      <body class="bg-slate-50 font-['Inter'] p-8">
        <div class="max-w-2xl mx-auto bg-white shadow-sm border border-slate-200 rounded-xl overflow-hidden">
          <div class="bg-orange-500 p-8 text-white">
            <h1 class="text-3xl font-bold">RSS Feed</h1>
            <p class="opacity-90 mt-2">Subscribe to the latest analytics projects by Mohit Shrestha.</p>
            <div class="mt-4 text-xs font-mono bg-orange-600/50 p-2 rounded">
                Copy this URL into your RSS reader
            </div>
          </div>
          <div class="p-6">
            <xsl:for-each select="rss/channel/item">
              <div class="mb-8 last:mb-0 pb-8 last:pb-0 border-b border-slate-100 last:border-0">
                <a href="{link}" class="text-xl font-bold text-slate-900 hover:text-orange-600 transition-colors">
                  <xsl:value-of select="title"/>
                </a>
                <p class="text-slate-500 text-sm mt-2 leading-relaxed">
                  <xsl:value-of select="description"/>
                </p>
                <div class="mt-3 flex items-center text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  <xsl:value-of select="pubDate"/>
                </div>
              </div>
            </xsl:for-each>
          </div>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>