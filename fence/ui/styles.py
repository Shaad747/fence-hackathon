"""Fence's single stylesheet, scoped to the Streamlit shell."""

STYLES = """<style>
/* Hallmark · v2.0.0 · modern-minimal · shape: app screen · theme: The Decision Brief (Fence navy and mint) · redesign: app, opening and report */
/* Critique: The proposal leads into two readings. The cited case is the evidence, with its audit details one level deeper. */
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,600..700,0..100&family=Hanken+Grotesk:wght@400..600&display=swap');

:root {
    --base: #0F1A33;
    --surface: #192745;
    --edge: #677793;
    --input: #101d35;
    --input-focus: #1c2b48;
    --accent-ink: #0b2230;
    --action-hover: #a2e9d9;
    --legacy-input: rgba(10,19,38,.72);
    --legacy-glass: rgba(15,26,51,.72);
    --legacy-expander: rgba(20,34,60,.88);
    --legacy-panel: rgba(15,26,51,.68);
    --brief-rule: #445473;
    --quiet-rule: #ffffff12;
    --glass: rgba(255,255,255,.08);
    --glass-strong: rgba(255,255,255,.14);
    --glass-border: rgba(255,255,255,.18);
    --safe: #7FD6C2;
    --warn: #F2B84B;
    --danger: #F0766B;
    --text: #E8ECF8;
    --text-dim: #9AA6C7;
    --raised: inset 0 1px 0 rgba(255,255,255,.12), 0 24px 60px -24px rgba(5,10,30,.7);
    --nav-height: 56px;
    --gutter: 32px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --panel-radius: 12px;
    --heading: 'Fraunces', Georgia, serif;
    --body: 'Hanken Grotesk', system-ui, sans-serif;
}

html, body { overflow-x: clip; }
.stApp { background: var(--base); color: var(--text); }

[data-testid='stHeader'], [data-testid='stToolbar'], [data-testid='stDecoration'], #MainMenu,
[data-testid='stHeaderActionElements'] { display: none !important; }
.stMainBlockContainer {
    position: relative; z-index: 1; max-width: 1250px;
    padding: var(--nav-height) var(--gutter) 52px;
}
.stApp, .stApp p, .stApp label, .stApp button, .stApp textarea,
.stApp [data-baseweb='select'], [data-baseweb='popover'] { font-family: var(--body); }
.stApp p, .stApp li { line-height: 1.6; }
.stApp h1, .stApp h2, .stApp h3 {
    font-family: var(--heading); font-weight: 650; font-optical-sizing: auto;
    font-variation-settings: 'SOFT' 65; letter-spacing: -.04em; color: var(--text);
}
.stApp a { color: var(--safe); text-underline-offset: 4px; }
.stApp :is(a, button, textarea, input, [role='combobox']):focus-visible,
.stApp [data-baseweb='select']:has([role='combobox']:focus-visible),
.stApp [data-testid='stExpander']:has(summary:focus-visible) {
    outline: 2px solid var(--safe) !important; outline-offset: 2px;
}
.stApp [data-testid='stExpander']:has(summary:focus-visible) { border-radius: 14px; }
.stApp :is(h2[id], h3[id], .fence-anchor) { scroll-margin-top: calc(var(--nav-height) + var(--space-6)); }
.fence-anchor { display: block; height: 0; }

.fence-nav {
    position: fixed; inset: 0 0 auto; z-index: 50;
    background: var(--base); border-bottom: 1px solid var(--glass-border);
}
.fence-nav-inner {
    max-width: 1250px; padding: 0 var(--gutter); margin: auto; min-height: var(--nav-height);
    display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
}
.fence-nav a { text-decoration: none; }
.fence-nav .fence-brand {
    display: inline-flex; align-items: center; gap: var(--space-2); min-height: 44px;
    font-family: var(--heading); font-size: 24px; font-weight: 700; color: var(--text);
}
.fence-brand svg, .fence-brand span { color: var(--safe); }
.fence-brand span { margin-left: calc(-1 * var(--space-2)); }
.fence-nav nav { display: flex; align-items: center; gap: 4px; }
.fence-nav nav a {
    display: inline-flex; align-items: center; justify-content: center; min-width: 44px; min-height: 44px;
    padding: 0 var(--space-2); color: var(--text-dim); font-size: 14px; font-weight: 600; white-space: nowrap;
    border-radius: 8px;
}
.fence-nav nav a[href="#check"] { color: var(--safe); }
.fence-nav nav a:hover, .fence-nav nav a:active { color: var(--text); background: var(--surface); }

.st-key-fence-hero {
    padding: 32px 0 var(--space-6);
    border-bottom: 1px solid var(--glass-border);
}
.st-key-fence-hero [data-testid='stColumn'] { min-width: 0; }
.stApp .fence-hero-copy h1, .stApp .fence-preview h2 {
    font-family: var(--body); font-weight: 600; letter-spacing: -.02em;
    overflow-wrap: break-word; min-width: 0; text-wrap: balance;
}
.stApp .fence-hero-copy h1 { font-size: 36px; line-height: 1.12; padding: 0; margin: 0 0 var(--space-2); }
.stApp .fence-intro { font-size: 16px; color: var(--text-dim); max-width: 65ch; margin: 0; }
.st-key-fence-proposal-panel, .fence-preview {
    border: 1px solid var(--glass-border); border-radius: var(--panel-radius); padding: var(--space-6);
}
.st-key-fence-proposal-panel { background: var(--surface); color: var(--text); }
.stApp .st-key-fence-proposal-panel [data-testid='stTextAreaRootElement'] {
    border-color: var(--edge); background: var(--input); color: var(--text); border-radius: 8px;
}
.stApp .st-key-fence-proposal-panel [data-testid='stTextAreaRootElement']:focus-within {
    border-color: var(--safe); background: var(--input-focus);
}
.stApp .st-key-fence-proposal-actions [data-testid='stButton'] button,
.stApp .st-key-fence-proposal-status [data-testid='stButton'] button { min-height: 44px; border-radius: 8px; white-space: nowrap; }
.st-key-fence-proposal-status [data-testid='stAlert'] { overflow-wrap: anywhere; }
.st-key-fence-proposal-status:not(:has([data-testid='stAlert'], .fence-loading, button)) { display: none; }
.st-key-fence-proposal-actions button:disabled,
.st-key-fence-proposal-status button:disabled { cursor: not-allowed; }
.st-key-fence-proposal-actions button:not(:disabled):active,
.st-key-fence-proposal-status button:not(:disabled):active { filter: brightness(.9); }
.stApp [data-testid='stCaptionContainer'] { opacity: 1; }
.stApp [data-testid='stCaptionContainer'] p {
    color: color-mix(in srgb, var(--text-dim), var(--text) 40%); font-size: 14px;
}
.stApp [data-testid='stWidgetLabel'] p { color: var(--text); font-weight: 600; font-size: 16px; }
.stApp [data-baseweb='textarea'], .stApp [data-baseweb='select'] > div {
    border-radius: 14px; background: var(--legacy-input); border: 1px solid var(--glass-border);
    color: var(--text); transition: background-color 200ms ease-out, border-color 200ms ease-out;
}
.stApp [data-baseweb='textarea']:focus-within, .stApp [data-baseweb='select'] > div:focus-within {
    background: var(--input-focus); border-color: var(--safe);
}
.stApp textarea { background: transparent; color: var(--text); font-size: 16px; }
.stApp textarea::placeholder { color: var(--text-dim); opacity: 1; }
.stApp [data-testid='stButton'] button {
    min-height: 48px; border-radius: 14px; font-weight: 600;
    transition: background-color 200ms ease-out, border-color 200ms ease-out, color 200ms ease-out;
}
.stApp [data-testid='stBaseButton-primary'] { background: var(--safe); border-color: var(--safe); color: var(--accent-ink); }
.stApp [data-testid='stBaseButton-primary']:hover { background: var(--action-hover); border-color: var(--action-hover); color: var(--accent-ink); }
.stApp [data-testid='stBaseButton-secondary'] { background: var(--glass); border-color: var(--glass-border); color: var(--text); }
.stApp [data-testid='stBaseButton-secondary']:hover { background: var(--glass-strong); border-color: var(--safe); color: var(--text); }

.fence-preview { margin: 0; }
.fence-meta, .fence-count, .fence-footer { font-size: 14px; color: var(--text-dim); }
.stApp .fence-preview h2 { margin: 0 0 4px; padding: 0; font-size: 24px; line-height: 1.2; }
.fence-preview .fence-meta { margin: 0 0 var(--space-4); }
.stApp .fence-preview-outcome {
    padding: var(--space-3) 0; border-block: 1px solid var(--glass-border);
    color: var(--text); font-size: 16px; font-weight: 600; margin: 0 0 var(--space-3);
}
.fence-preview-outcome span { font-weight: 400; }
.fence-preview-reason { color: var(--text-dim); font-size: 16px; margin: 0 0 var(--space-3); }
.fence-preview a { display: inline-flex; align-items: center; min-height: 44px; font-size: 14px; font-weight: 600; }

.st-key-fence-problem, .st-key-fence-archive, .fence-how {
    border-top: 1px solid var(--glass-border); padding: 52px 0 30px; margin-top: 28px;
}
.stApp .fence-section-title { font-size: 44px; line-height: 1.1; padding: 0; margin: 0 0 var(--space-2); }
.stApp .fence-section-lede { font-size: 20px; color: var(--text-dim); max-width: 65ch; margin-bottom: 14px; }
.fence-beats p { max-width: 62ch; margin: 0; padding: var(--space-3) 0; border-bottom: 1px solid var(--quiet-rule); color: var(--text-dim); }
.fence-beats strong { color: var(--text); font-weight: 600; }
.fence-stat { padding: 25px 28px; margin: 0; border-radius: 20px; border: 1px solid var(--glass-border);
    box-shadow: var(--raised); backdrop-filter: blur(22px) saturate(140%);
    background: linear-gradient(148deg, var(--glass-strong), var(--glass)), var(--legacy-glass);
}
.fence-stat strong { display: block; font: 650 72px/.98 var(--heading); letter-spacing: -.05em; color: var(--danger); margin: var(--space-3) 0; }
.fence-stat p { font-size: 20px; margin: 0 0 14px; }
.fence-stat figcaption { font-size: 14px; color: var(--text-dim); }

.st-key-fence-archive [data-testid='stButton'] { width: fit-content; }
.stApp [data-testid='stExpander'] details { border: 1px solid var(--glass-border); border-radius: 14px; background: var(--legacy-expander); }
.stApp [data-testid='stExpander'] summary { min-height: 52px; border-radius: 14px; transition: background-color 200ms ease-out; }
.stApp [data-testid='stExpander'] summary:hover { background: var(--glass); }
.stApp :is(.st-key-fence-timeline, [class*="st-key-fence-case-evidence-"]) [data-testid='stExpander'] details {
    background: var(--base); color: var(--text); border: 0; border-bottom: 1px solid var(--brief-rule); border-radius: 0;
}
.stApp :is(.st-key-fence-timeline, [class*="st-key-fence-case-evidence-"]) [data-testid='stExpander'] summary {
    border-radius: 0; min-height: 44px;
}
.st-key-fence-timeline { gap: 0; }
.st-key-fence-timeline summary [data-testid='stMarkdownContainer'] p { color: var(--text-dim); font-size: 14px; }
.st-key-fence-timeline summary strong {
    display: block; color: var(--text); font-family: var(--heading); font-weight: 650; font-size: 19px;
    min-width: 0; overflow-wrap: break-word;
}
.fence-decision-detail { color: var(--text-dim); padding: 4px 4px 0; overflow-wrap: anywhere; }
.fence-decision-detail dt { color: var(--text); font-weight: 600; margin-top: var(--space-3); }
.fence-decision-detail dd { margin: 2px 0 0; max-width: 72ch; }
.fence-decision-detail ul { margin: 4px 0 0; }
.fence-decision-detail .fence-chips { display: flex; flex-wrap: wrap; gap: var(--space-2); padding: 0; margin: var(--space-4) 0 var(--space-2); list-style: none; }
.fence-chip { border: 1px solid var(--glass-border); border-radius: 4px; padding: 0 var(--space-2); font-size: 14px; }

.fence-steps, .fence-planned { display: grid; gap: var(--space-3); margin: var(--space-5) 0; padding: 0; list-style: none; }
.fence-steps { grid-template-columns: repeat(3, 1fr); }
.fence-planned { grid-template-columns: 1fr 1fr; }
.fence-steps li, .fence-planned section {
    border: 1px solid var(--glass-border); border-radius: 20px; padding: var(--space-4) var(--space-5); background: var(--legacy-panel);
}
.fence-steps strong { font: 650 24px var(--heading); color: var(--safe); }
.fence-steps p, .fence-planned p { color: var(--text-dim); margin: 4px 0 0; }
.fence-planned h3 { font-size: 20px; padding: 0; margin: 0; }
.fence-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-3); margin-top: 34px; }

@media (max-width: 900px) {
    :root { --gutter: 24px; }
    .stApp [data-testid='stHorizontalBlock']:not(.st-key-fence-hero *, .st-key-fence-readings *, .st-key-fence-archive-filters *) { flex-direction: column; gap: var(--space-3); }
    .stApp [data-testid='stHorizontalBlock']:not(.st-key-fence-hero *, .st-key-fence-readings *, .st-key-fence-archive-filters *) > [data-testid='stColumn'] {
        width: 100% !important; flex: 1 1 100%; min-width: 0;
    }
    .st-key-fence-archive-filters [data-testid='stHorizontalBlock'] {
        display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3);
    }
    .st-key-fence-archive-filters [data-testid='stColumn'] { width: 100% !important; min-width: 0; }
    .fence-steps, .fence-planned { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
    :is(.st-key-fence-hero, .st-key-fence-readings) [data-testid='stHorizontalBlock'] {
        flex-direction: column; gap: var(--space-4);
    }
    :is(.st-key-fence-hero, .st-key-fence-readings) [data-testid='stColumn'] { width: 100% !important; flex: 1 1 100%; }
}
@media (max-width: 600px) {
    :root { --nav-height: 88px; --gutter: 16px; }
    .stMainBlockContainer { padding-bottom: 28px; }
    .fence-nav-inner { gap: var(--space-2); }
    .fence-nav nav { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0; }
    .fence-nav nav a { font-size: 12px; padding-inline: 4px; }
    .fence-nav .fence-brand { font-size: 20px; }
    .fence-brand svg { width: 20px; height: 20px; }
    .st-key-fence-hero { padding-top: var(--space-4); }
    .stApp .fence-hero-copy h1 { font-size: 28px; }
    .st-key-fence-proposal-panel, .fence-preview { padding: var(--space-4); }
    .stApp .fence-section-lede { font-size: 16px; }
    .stApp .fence-section-title { font-size: 32px; }
    .fence-stat { padding: var(--space-5); }
    .st-key-fence-problem, .st-key-fence-archive, .fence-how { padding-top: 36px; }
}
@media (max-width: 420px) {
    .st-key-fence-proposal-actions { flex-direction: column; align-items: stretch; }
    .st-key-fence-proposal-actions > [data-testid='stElementContainer'],
    .st-key-fence-proposal-actions [data-testid='stButton'],
    .st-key-fence-proposal-actions [data-testid='stButton'] button { width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
    .stApp *, .stApp *::before, .stApp *::after { transition-duration: 0s !important; scroll-behavior: auto !important; }
}
#fence-report-heading {
    font-family: var(--heading); font-size: 36px; min-width: 0; overflow-wrap: break-word;
}
.st-key-fence-report-summary {
    border-bottom: 1px solid var(--brief-rule); padding-bottom: var(--space-4); gap: var(--space-2);
}
.fence-reviewed-proposal { max-width: 78ch; margin: 0; overflow-wrap: anywhere; text-wrap: pretty; }
.fence-reviewed-proposal strong { margin-right: var(--space-2); }
.st-key-fence-readings [data-testid='stColumn'] { min-width: 0; }
.st-key-comparison_view [role='radiogroup'] { flex-wrap: wrap; }
.st-key-comparison_view [role='radiogroup'] label { min-height: 44px; }
.stApp :is(.st-key-fence-baseline, .st-key-fence-grounded) {
    border-top: 2px solid var(--brief-rule); padding: var(--space-5); overflow-wrap: anywhere; gap: var(--space-2);
}
.stApp .st-key-fence-grounded { border-top-color: var(--safe); background: var(--surface); color: var(--text); }
.stApp :is(.st-key-fence-baseline, .st-key-fence-grounded) h3 {
    font: 600 24px/1.2 var(--body); letter-spacing: normal;
}
.stApp :is(.st-key-fence-baseline, .st-key-fence-grounded) h4 {
    font: 600 16px/1.4 var(--body); padding: 0 0 4px;
}
.st-key-fence-readings :is(p, ol) { max-width: 70ch; }
.fence-risk-line { color: var(--text-dim); font-size: 14px; }
.fence-risk-line .fence-risk { margin-right: var(--space-2); }
.fence-risk { display: inline-block; color: var(--warn); font-weight: 600; }
.fence-risk-low { color: var(--safe); }
.fence-precedent { border-top: 1px solid var(--brief-rule); padding-top: var(--space-3); }
.fence-precedent ul { list-style: none; padding: 0; margin: 0 0 4px; }
.stApp a.fence-citation {
    color: var(--safe); text-decoration: underline; text-underline-offset: 4px;
    font-weight: 600; overflow-wrap: anywhere;
}
.stApp .fence-case-heading { font: 600 20px/1.3 var(--body); letter-spacing: normal; }
.fence-case {
    padding-top: var(--space-4); border-top: 1px solid var(--brief-rule);
    scroll-margin-top: calc(var(--nav-height) + var(--space-6)); overflow-wrap: anywhere;
}
.fence-case:focus { outline: 2px solid var(--safe); outline-offset: 4px; }
.stApp .fence-case h4 {
    font: 650 24px/1.25 var(--heading); padding: 0;
    min-width: 0; overflow-wrap: break-word;
}
.fence-case p { max-width: 72ch; margin-bottom: var(--space-2); }
.fence-case-meta {
    display: flex; flex-wrap: wrap; column-gap: var(--space-4); row-gap: 4px;
    color: var(--text-dim); font-size: 14px;
}
.fence-case-status { color: var(--text); font-weight: 600; }
[class*="st-key-fence-case-evidence-"] [data-testid='stProgress'] { max-width: 36ch; }
.fence-source-excerpt { white-space: pre-wrap; max-width: 75ch; }
.stApp [data-testid='stMarkdownContainer'] p { overflow-wrap: anywhere; }
.stApp .fence-loading {
    border: 1px solid var(--edge); border-radius: 8px; padding: var(--space-3);
    background: var(--input); margin: 0;
}
@media (max-width: 600px) {
    #fence-report-heading { font-size: 28px; }
    .fence-reviewed-proposal strong { display: block; }
    .stApp :is(.st-key-fence-baseline, .st-key-fence-grounded) { padding: var(--space-4); }
}
</style>"""
